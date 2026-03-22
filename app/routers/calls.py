from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.utils.helpers import get_verified_user
from app.core.config import settings
import time
import logging
import uuid as uuid_lib
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calls", tags=["Calls"])

# ── Generate Agora Token ──────────────────────────────────────
@router.post("/token")
def generate_call_token(
    channel_name: str,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    app_id = settings.AGORA_APP_ID
    app_certificate = settings.AGORA_APP_CERTIFICATE

    if not app_id:
        raise HTTPException(status_code=500, detail="AGORA_APP_ID missing")
    if not app_certificate:
        raise HTTPException(status_code=500, detail="AGORA_APP_CERTIFICATE missing")

    try:
        from agora_token_builder import RtcTokenBuilder
        expiry = int(time.time()) + 3600
        try:
            token = RtcTokenBuilder.buildTokenWithUid(
                app_id, app_certificate, channel_name, 0, 1, expiry, expiry)
        except TypeError:
            token = RtcTokenBuilder.buildTokenWithUid(
                app_id, app_certificate, channel_name, 0, 1, expiry)

        return {"token": token, "channel_name": channel_name, "app_id": app_id, "uid": 0}

    except ImportError:
        raise HTTPException(status_code=500, detail="agora_token_builder package missing.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Token generation failed: {str(e)}")


# ── Notify receiver + Save call log ──────────────────────────
@router.post("/initiate")
async def initiate_call(
    receiver_id: str,
    channel_name: str,
    call_type: str = "audio",
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    from app.models.call_log import CallLog, CallType, CallStatus

    call_log_id = None

    # ✅ Call log save karo
    try:
        call_log = CallLog(
            caller_id=current_user.id,
            receiver_id=uuid_lib.UUID(receiver_id),
            channel_name=channel_name,
            call_type=CallType.audio if call_type == "audio" else CallType.video,
            status=CallStatus.missed,
        )
        db.add(call_log)
        db.commit()
        db.refresh(call_log)
        call_log_id = str(call_log.id)
        logger.info(f"Call log saved: {call_log_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"Call log save error: {e}")

    # ✅ Notification alag try mein
    try:
        from app.models.notification import Notification, NotifType
        notif = Notification(
            user_id=receiver_id,
            type=NotifType.message,
            message=f"{current_user.full_name} is calling you ({call_type})"
        )
        db.add(notif)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Notification save error: {e}")

    # ✅ WebSocket se notify karo
    try:
        from app.routers.chat import manager
        await manager.send_to_user(receiver_id, {
            "type": "incoming_call",
            "caller_id": str(current_user.id),
            "caller_name": current_user.full_name,
            "channel_name": channel_name,
            "call_type": call_type,
            "call_log_id": call_log_id,
        })
    except Exception as e:
        logger.error(f"WebSocket notify error: {e}")

    # ✅ FCM Push Notification — agar receiver offline hai
    try:
        from app.services.firebase import send_push_notification
        receiver = db.query(User).filter(
            User.id == uuid_lib.UUID(receiver_id)
        ).first()
        if receiver and receiver.fcm_token:
            send_push_notification(
                fcm_token=receiver.fcm_token,
                title=f"📞 Incoming {call_type.capitalize()} Call",
                body=f"{current_user.full_name} is calling you",
                data={
                    "type": "call",
                    "call_type": call_type,
                    "caller_id": str(current_user.id),
                    "caller_name": current_user.full_name,
                    "channel_id": channel_name,
                    "call_log_id": call_log_id or "",
                }
            )
            logger.info(f"FCM call notification sent to {receiver_id}")
    except Exception as e:
        logger.error(f"FCM call notification error: {e}")

    return {
        "message": "Call initiated",
        "channel_name": channel_name,
        "call_log_id": call_log_id
    }


# ── Call accept ───────────────────────────────────────────────
@router.post("/accept")
async def accept_call(
    call_log_id: str,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    from app.models.call_log import CallLog, CallStatus
    try:
        log = db.query(CallLog).filter(CallLog.id == uuid_lib.UUID(call_log_id)).first()
        if log:
            log.status = CallStatus.completed
            db.commit()
    except Exception as e:
        logger.error(f"Accept call error: {e}")
    return {"message": "Call accepted"}


# ── Call end ──────────────────────────────────────────────────
@router.post("/end")
async def end_call(
    call_log_id: str,
    duration_seconds: int = 0,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    from app.models.call_log import CallLog, CallStatus
    try:
        log = db.query(CallLog).filter(CallLog.id == uuid_lib.UUID(call_log_id)).first()
        if log:
            if duration_seconds > 0:
                log.status = CallStatus.completed
                log.duration_seconds = str(duration_seconds)
            db.commit()
    except Exception as e:
        logger.error(f"End call error: {e}")
    return {"message": "Call ended"}


# ── Call decline ──────────────────────────────────────────────
@router.post("/decline")
async def decline_call(
    call_log_id: str,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    from app.models.call_log import CallLog, CallStatus
    try:
        log = db.query(CallLog).filter(CallLog.id == uuid_lib.UUID(call_log_id)).first()
        if log:
            log.status = CallStatus.declined
            db.commit()
    except Exception as e:
        logger.error(f"Decline call error: {e}")
    return {"message": "Call declined"}


# ── Call history ──────────────────────────────────────────────
@router.get("/history")
def get_call_history(
    limit: int = 30,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    from app.models.call_log import CallLog
    from app.models.profile import Profile

    try:
        logs = db.query(CallLog).filter(
            (CallLog.caller_id == current_user.id) |
            (CallLog.receiver_id == current_user.id)
        ).order_by(CallLog.created_at.desc()).limit(limit).all()

        result = []
        for log in logs:
            is_outgoing = log.caller_id == current_user.id
            other_id = log.receiver_id if is_outgoing else log.caller_id

            # ✅ Pehle profile table se naam lo
            other_name = None
            other_photo = None

            try:
                profile = db.query(Profile).filter(
                    Profile.user_id == other_id
                ).first()
                if profile:
                    other_name = getattr(profile, "full_name", None)
                    other_photo = profile.profile_photo
            except Exception as e:
                logger.error(f"Profile fetch error: {e}")

            # ✅ Profile nahi mila toh user table se lo
            if not other_name:
                try:
                    other_user = db.query(User).filter(
                        User.id == other_id
                    ).first()
                    if other_user:
                        other_name = other_user.full_name
                except Exception as e:
                    logger.error(f"User fetch error: {e}")

            # ✅ Phir bhi nahi mila toh Unknown
            if not other_name:
                other_name = "Unknown"

            # ✅ created_at UTC se ISO format mein bhejo
            created_at_str = None
            if log.created_at:
                dt = log.created_at
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                created_at_str = dt.isoformat()

            result.append({
                "id": str(log.id),
                "other_user_id": str(other_id),
                "other_user_name": other_name,
                "other_user_photo": other_photo,
                "call_type": log.call_type if isinstance(log.call_type, str) else log.call_type.value,
                "status": log.status if isinstance(log.status, str) else log.status.value,
                "is_outgoing": is_outgoing,
                "duration_seconds": log.duration_seconds or "0",
                "created_at": created_at_str,
            })

        return result

    except Exception as e:
        logger.error(f"Call history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))