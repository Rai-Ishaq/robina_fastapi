from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.models.notification import Notification
from app.utils.helpers import get_verified_user
from app.services.firebase import send_push_notification

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.post("/save-token")
def save_fcm_token(
    token_data: dict,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    fcm_token = token_data.get("fcm_token")
    if not fcm_token:
        return {"message": "Token required"}
    current_user.fcm_token = fcm_token
    db.commit()
    return {"message": "FCM token saved"}


@router.post("/test-push")
def test_push(
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    if not current_user.fcm_token:
        return {"error": "No FCM token found"}
    success = send_push_notification(
        fcm_token=current_user.fcm_token,
        title="Test ✅",
        body="Push notifications working!",
        data={"type": "test"}
    )
    return {"success": success}


@router.get("/")
def get_notifications(
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    notifs = db.query(Notification).filter(
        Notification.user_id == current_user.id
    ).order_by(Notification.created_at.desc()).limit(50).all()
    return [
        {
            "id": str(n.id),
            "type": n.type,
            "message": n.message,
            "is_read": n.is_read,
            "created_at": str(n.created_at)
        }
        for n in notifs
    ]


@router.put("/read-all")
def mark_all_read(
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False
    ).update({"is_read": True})
    db.commit()
    return {"message": "All marked as read"}


# FIX: clear-all BEFORE /{notif_id} — warna FastAPI "clear-all" ko ID samajhta hai
@router.delete("/clear-all")
def clear_all_notifications(
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    db.query(Notification).filter(
        Notification.user_id == current_user.id
    ).delete()
    db.commit()
    return {"message": "All notifications cleared"}


@router.put("/{notif_id}/read")
def mark_read(
    notif_id: str,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    notif = db.query(Notification).filter(
        Notification.id == notif_id,
        Notification.user_id == current_user.id
    ).first()
    if notif:
        notif.is_read = True
        db.commit()
    return {"message": "Marked as read"}


@router.delete("/{notif_id}")
def delete_notification(
    notif_id: str,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    db.query(Notification).filter(
        Notification.id == notif_id,
        Notification.user_id == current_user.id
    ).delete()
    db.commit()
    return {"message": "Notification deleted"}