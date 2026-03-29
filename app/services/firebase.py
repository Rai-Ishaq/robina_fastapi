import firebase_admin
from firebase_admin import credentials, messaging
import os
import json

if not firebase_admin._apps:
    creds_json = os.environ.get("FIREBASE_CREDENTIALS")
    if creds_json:
        # Render par — env variable se
        cred_dict = json.loads(creds_json)
        cred = credentials.Certificate(cred_dict)
    else:
        # Local — file se
        cred = credentials.Certificate("firebase_service_account.json")
    firebase_admin.initialize_app(cred)


def send_push_notification(fcm_token: str, title: str, body: str, data: dict = {}):
    """Regular notifications (messages, interests, etc.) ke liye"""
    if not fcm_token:
        return False
    try:
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data={k: str(v) for k, v in data.items()},
            token=fcm_token,
            android=messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    sound="default",
                    priority="high",
                    channel_id="high_importance_channel",
                )
            ),
        )
        response = messaging.send(message)
        print(f"✅ Notification sent: {response}")
        return True
    except Exception as e:
        print(f"❌ FCM Error: {e}")
        return False


def send_call_notification(fcm_token: str, data: dict = {}):
    """
    ✅ Call notifications ke liye DATA-ONLY FCM message
    
    notification field include NAHI karte — warna Android system notification
    dikhata hai aur flutter_callkit_incoming ka full-screen UI nahi chalta.
    Data-only + high priority = background handler properly chalta hai
    aur CallKit Accept/Decline screen automatically show hoti hai.
    """
    if not fcm_token:
        return False
    try:
        message = messaging.Message(
            # ✅ notification field BILKUL nahi — data-only message
            data={k: str(v) for k, v in data.items()},
            token=fcm_token,
            android=messaging.AndroidConfig(
                priority="high",           # ✅ Zaroori: background handler wake karo
                ttl=30,                    # 30 seconds — call expire ho jaye
            ),
            apns=messaging.APNSConfig(    # iOS ke liye
                headers={
                    "apns-priority": "10",            # ✅ High priority
                    "apns-push-type": "background",   # ✅ Background wake-up
                    "apns-expiration": "30",           # 30 sec
                },
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        content_available=True,  # ✅ iOS ko background mein wake karo
                        sound="default",
                    )
                ),
            ),
        )
        response = messaging.send(message)
        print(f"✅ Call notification sent: {response}")
        return True
    except Exception as e:
        print(f"❌ Call FCM Error: {e}")
        return False