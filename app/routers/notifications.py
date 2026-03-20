from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.models.notification import Notification
from app.utils.helpers import get_verified_user

router = APIRouter(prefix="/notifications", tags=["Notifications"])

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
    return {"message": "All notifications marked as read"}

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