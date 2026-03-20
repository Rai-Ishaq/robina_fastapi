from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.models.profile import Profile
from app.models.interest import Interest, InterestStatus
from app.models.notification import Notification, NotifType
from app.schemas.interest import SendInterestRequest, InterestActionRequest
from app.utils.helpers import get_verified_user
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot send interest to yourself"
        )

    existing = db.query(Interest).filter(
        Interest.sender_id == current_user.id,
        Interest.receiver_id == request.receiver_id,
        Interest.status == InterestStatus.pending
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Interest already sent"
        )

    interest = Interest(
        sender_id=current_user.id,
        receiver_id=request.receiver_id
    )
    db.add(interest)

    notif = Notification(
        user_id=request.receiver_id,
        type=NotifType.interest,
        message=f"{current_user.full_name} sent you an interest"
    )
    db.add(notif)
    db.commit()

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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interest not found"
        )

    if request.action == "accept":
        interest.status = InterestStatus.accepted
        notif_msg = f"{current_user.full_name} accepted your interest"
        notif_type = NotifType.accepted
    elif request.action == "decline":
        interest.status = InterestStatus.declined
        notif_msg = f"{current_user.full_name} declined your interest"
        notif_type = NotifType.interest
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Action must be accept or decline"
        )

    interest.updated_at = datetime.utcnow()

    notif = Notification(
        user_id=interest.sender_id,
        type=notif_type,
        message=notif_msg
    )
    db.add(notif)
    db.commit()

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
        age = today.year - dob.year - (
            (today.month, today.day) < (dob.month, dob.day)
        )
    return {
        "id": str(interest.id),
        "sender_id": str(interest.sender_id),
        "receiver_id": str(interest.receiver_id),
        "status": interest.status,
        "sender_name": user.full_name,
        "sender_city": profile.city if profile else None,
        "sender_photo": profile.profile_photo if profile else None,
        "sender_age": age,
        "created_at": str(interest.created_at)
    }