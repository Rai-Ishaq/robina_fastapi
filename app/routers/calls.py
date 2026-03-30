import time
from agora_token_builder import RtcTokenBuilder
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc
from app.database import get_db
from app.models.user import User
from app.models.call_log import CallLog, CallStatus, CallType
from app.models.profile import Profile
from app.utils.helpers import get_verified_user
from app.core.config import settings
from app.services.firebase import send_call_notification
from app.routers.chat import manager

router = APIRouter(prefix="/calls", tags=["Calls"])


@router.post("/token")
def get_agora_token(
    channel_name: str,
    uid: int,
    current_user: User = Depends(get_verified_user),
):
    expire = int(time.time()) + 3600
    token = RtcTokenBuilder.buildTokenWithUid(
        settings.AGORA_APP_ID,
        settings.AGORA_APP_CERTIFICATE,
        channel_name,
        uid,
        1,  # Role_Publisher = 1
        expire,
    )
    return {"token": token, "app_id": settings.AGORA_APP_ID}


@router.post("/initiate")
async def initiate_call(
    receiver_id: str,
    channel_name: str,
    call_type: str = "audio",
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    receiver = db.query(User).filter(User.id == receiver_id).first()
    if not receiver:
        return {"error": "Receiver not found"}

    # Get caller profile photo
    caller_profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    caller_photo = caller_profile.profile_photo if caller_profile else None

    call_log = CallLog(
        caller_id=current_user.id,
        receiver_id=receiver_id,
        call_type=CallType.video if call_type == "video" else CallType.audio,
        status=CallStatus.missed,   # Default missed — updated on accept/end
        channel_name=channel_name,
    )
    db.add(call_log)
    db.commit()
    db.refresh(call_log)

    call_data = {
        "type": "incoming_call",
        "call_log_id": str(call_log.id),
        "caller_id": str(current_user.id),
        "caller_name": current_user.full_name or "User",
        "caller_photo": caller_photo or "",
        "channel_name": channel_name,
        "call_type": call_type,
    }

    await manager.send_to(str(receiver_id), call_data)

    if receiver.fcm_token:
        send_call_notification(
            fcm_token=receiver.fcm_token,
            data={
                "type": "call",
                "call_log_id": str(call_log.id),
                "caller_id": str(current_user.id),
                "caller_name": current_user.full_name or "User",
                "caller_photo": caller_photo or "",
                "channel_id": channel_name,
                "call_type": call_type,
            },
        )

    return {
        "call_log_id": str(call_log.id),
        "channel_name": channel_name,
        "app_id": settings.AGORA_APP_ID,
    }


@router.post("/accept")
def accept_call(
    call_log_id: str,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    log = db.query(CallLog).filter(CallLog.id == call_log_id).first()
    if log:
        log.status = CallStatus.completed  # Mark as answered
        db.commit()

        # Notify caller that call was accepted
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(manager.send_to(str(log.caller_id), {
                "type": "call_accepted",
                "call_log_id": call_log_id,
            }))
        except Exception:
            pass

    return {"success": True}


@router.post("/decline")
async def decline_call(
    call_log_id: str,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    log = db.query(CallLog).filter(CallLog.id == call_log_id).first()
    if log:
        log.status = CallStatus.declined
        db.commit()
        await manager.send_to(str(log.caller_id), {
            "type": "call_declined",
            "call_log_id": call_log_id,
        })
    return {"success": True}


@router.post("/end")
async def end_call(
    call_log_id: str,
    duration_seconds: int = 0,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    log = db.query(CallLog).filter(CallLog.id == call_log_id).first()
    if log:
        if log.status == CallStatus.missed:
            pass  # Stay missed if never answered
        else:
            log.status = CallStatus.completed
        log.duration_seconds = str(duration_seconds)
        db.commit()

        other_id = str(log.receiver_id) if str(log.caller_id) == str(current_user.id) else str(log.caller_id)
        await manager.send_to(other_id, {
            "type": "call_ended",
            "call_log_id": call_log_id,
            "duration_seconds": duration_seconds,
        })
    return {"success": True}


@router.get("/history")
def get_call_history(
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    logs = db.query(CallLog).filter(
        or_(CallLog.caller_id == current_user.id, CallLog.receiver_id == current_user.id)
    ).order_by(desc(CallLog.created_at)).limit(100).all()

    result = []
    for log in logs:
        is_outgoing = str(log.caller_id) == str(current_user.id)
        other_id = log.receiver_id if is_outgoing else log.caller_id
        other = db.query(User).filter(User.id == other_id).first()
        if not other:
            continue
        profile = db.query(Profile).filter(Profile.user_id == other_id).first()
        status_val = log.status.value if log.status else "missed"
        is_missed = (status_val == "missed") and not is_outgoing

        result.append({
            "id": str(log.id),
            "other_user_id": str(other_id),
            "other_user_name": other.full_name or "User",
            "other_user_photo": profile.profile_photo if profile else None,
            "call_type": log.call_type.value if log.call_type else "audio",
            "status": status_val,
            "is_outgoing": is_outgoing,
            "is_missed": is_missed,
            "duration_seconds": int(log.duration_seconds or 0),
            "is_seen": log.is_seen,
            "created_at": log.created_at.isoformat(),
        })
    return result


@router.post("/mark-seen")
def mark_calls_seen(
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    db.query(CallLog).filter(
        CallLog.receiver_id == current_user.id,
        CallLog.status == CallStatus.missed,
        CallLog.is_seen == False,
    ).update({"is_seen": True})
    db.commit()
    return {"success": True}


@router.delete("/{call_log_id}")
def delete_call(
    call_log_id: str,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    log = db.query(CallLog).filter(
        CallLog.id == call_log_id,
        or_(CallLog.caller_id == current_user.id, CallLog.receiver_id == current_user.id),
    ).first()
    if log:
        db.delete(log)
        db.commit()
    return {"success": True}