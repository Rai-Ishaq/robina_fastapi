"""
Notification helper — har jagah se call karo
interests.py, profile.py, chat.py, calls.py mein use karo
"""
from sqlalchemy.orm import Session
from app.models.notification import Notification
from app.models.user import User
from app.services.firebase import send_push_notification
import uuid


def notify_user(
    db: Session,
    receiver_id: str,        # jis user ko notification jaaye
    sender_name: str,        # kisne kiya (display ke liye)
    notif_type: str,         # 'interest' | 'interest_accepted' | 'profile_view' | 'message' | 'call'
    message: str,            # notification text
    data: dict = None,       # extra data for FCM payload
):
    """
    1. DB mein notification record banao
    2. FCM push notification bhejo (agar token hai)
    """
    if data is None:
        data = {}

    # 1. DB record
    notif = Notification(
        id=str(uuid.uuid4()),
        user_id=receiver_id,
        type=notif_type,
        message=message,
        sender_name=sender_name,
        is_read=False,
    )
    db.add(notif)
    db.commit()

    # 2. FCM push
    receiver = db.query(User).filter(User.id == receiver_id).first()
    if receiver and receiver.fcm_token:
        # Title by type
        title_map = {
            'interest': '💚 New Interest',
            'interest_accepted': '✅ Interest Accepted',
            'profile_view': '👁️ Profile Viewed',
            'message': '💬 New Message',
            'call': '📞 Incoming Call',
        }
        title = title_map.get(notif_type, '🔔 Robina')

        send_push_notification(
            fcm_token=receiver.fcm_token,
            title=title,
            body=message,
            data={
                "type": notif_type,
                "sender_name": sender_name,
                "notification_id": str(notif.id),
                **data,
            }
        )

    return notif