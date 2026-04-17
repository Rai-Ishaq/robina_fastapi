from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.models.profile import Profile
from app.models.interest import Interest, InterestStatus
from app.models.notification import Notification, NotifType
from app.schemas.interest import SendInterestRequest, InterestActionRequest
from app.utils.helpers import get_verified_user
from app.services.firebase import send_push_notification
from datetime import datetime

router = APIRouter(prefix="/interests", tags=["Interests"])


# ── SEND INTEREST ─────────────────────────────────────────────
@router.post("/send")
def send_interest(
    request: SendInterestRequest,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    if str(current_user.id) == request.receiver_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot send interest to yourself")

    existing = db.query(Interest).filter(
        Interest.sender_id == current_user.id,
        Interest.receiver_id == request.receiver_id,
        Interest.status == InterestStatus.pending
    ).first()

    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Interest already sent")

    interest = Interest(sender_id=current_user.id, receiver_id=request.receiver_id)
    db.add(interest)

    notif = Notification(
        user_id=request.receiver_id,
        type=NotifType.interest,
        message=f"{current_user.full_name} sent you an interest"
    )
    db.add(notif)
    db.commit()

    # FCM Push
    receiver = db.query(User).filter(User.id == request.receiver_id).first()
    if receiver and receiver.fcm_token:
        send_push_notification(
            fcm_token=receiver.fcm_token,
            title="💚 New Interest",
            body=f"{current_user.full_name} sent you an interest",
            data={
                "type": "interest",
                "sender_id": str(current_user.id),
                "sender_name": current_user.full_name
            }
        )

    return {"message": "Interest sent successfully"}


# ── RESPOND TO INTEREST ───────────────────────────────────────
@router.put("/respond")
def respond_interest(
    request: InterestActionRequest,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    interest = db.query(Interest).filter(
        Interest.id == request.interest_id,
        Interest.receiver_id == current_user.id
    ).first()

    if not interest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interest not found")

    if request.action == "accept":
        interest.status = InterestStatus.accepted
        notif_msg = f"{current_user.full_name} accepted your interest"
        notif_type = NotifType.accepted
        push_title = "✅ Interest Accepted"
    elif request.action == "decline":
        interest.status = InterestStatus.declined
        notif_msg = f"{current_user.full_name} declined your interest"
        notif_type = NotifType.interest
        push_title = "Interest Update"
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Action must be accept or decline")

    interest.updated_at = datetime.utcnow()

    notif = Notification(
        user_id=interest.sender_id,
        type=notif_type,
        message=notif_msg
    )
    db.add(notif)
    db.commit()

    # FCM Push — sirf accept pe notify karo
    if request.action == "accept":
        sender = db.query(User).filter(User.id == interest.sender_id).first()
        if sender and sender.fcm_token:
            send_push_notification(
                fcm_token=sender.fcm_token,
                title=push_title,
                body=notif_msg,
                data={
                    "type": "interest_accepted",
                    "sender_id": str(current_user.id),
                    "sender_name": current_user.full_name
                }
            )

    return {"message": f"Interest {request.action}ed successfully"}


# ── GET RECEIVED ──────────────────────────────────────────────
@router.get("/received")
def get_received(
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    interests = db.query(Interest, User, Profile).join(
        User, User.id == Interest.sender_id
    ).outerjoin(
        Profile, Profile.user_id == Interest.sender_id
    ).filter(
        Interest.receiver_id == current_user.id,
        Interest.status == InterestStatus.pending
    ).all()
    return [_format_interest(i, u, p) for i, u, p in interests]


# ── GET SENT ──────────────────────────────────────────────────
@router.get("/sent")
def get_sent(
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    interests = db.query(Interest, User, Profile).join(
        User, User.id == Interest.receiver_id
    ).outerjoin(
        Profile, Profile.user_id == Interest.receiver_id
    ).filter(
        Interest.sender_id == current_user.id
    ).all()
    return [_format_interest(i, u, p) for i, u, p in interests]


# ── GET ACCEPTED ──────────────────────────────────────────────
@router.get("/accepted")
def get_accepted(
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    interests = db.query(Interest, User, Profile).join(
        User, User.id == Interest.sender_id
    ).outerjoin(
        Profile, Profile.user_id == Interest.sender_id
    ).filter(
        Interest.receiver_id == current_user.id,
        Interest.status == InterestStatus.accepted
    ).all()
    return [_format_interest(i, u, p) for i, u, p in interests]


# ── GET CANCELLED ─────────────────────────────────────────────
@router.get("/cancelled")
def get_cancelled(
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    interests = db.query(Interest, User, Profile).join(
        User, User.id == Interest.sender_id
    ).outerjoin(
        Profile, Profile.user_id == Interest.sender_id
    ).filter(
        Interest.receiver_id == current_user.id,
        Interest.status == InterestStatus.declined
    ).all()
    return [_format_interest(i, u, p) for i, u, p in interests]


def _format_interest(interest, user, profile):
    from datetime import date
    age = None
    if profile and profile.date_of_birth:
        today = date.today()
        dob = profile.date_of_birth
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    return {
        "id": str(interest.id),
        "sender_id": str(interest.sender_id),
        "receiver_id": str(interest.receiver_id),
        "status": interest.status,
        "sender_name": user.full_name,
        "sender_city": profile.city if profile else None,
        "sender_photo": profile.profile_photo if profile else None,
        "sender_age": age,
        "created_at": str(interest.created_at),
        "sender_verification_status": user.verification_status or "none",
        "sender_is_premium": user.is_premium or False
    }