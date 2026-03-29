from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from app.database import get_db, SessionLocal
from app.models.user import User
from app.models.message import Conversation, Message
from app.models.notification import Notification, NotifType
from app.models.profile import Profile
from app.schemas.message import SendMessageRequest
from app.utils.helpers import get_verified_user
from app.core.security import decode_token
from app.services.firebase import send_push_notification
from datetime import datetime
from typing import Dict, List
import json
import os
import cloudinary
import cloudinary.uploader

router = APIRouter(prefix="/chat", tags=["Chat"])

# Cloudinary config
cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME", ""),
    api_key=os.environ.get("CLOUDINARY_API_KEY", ""),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET", ""),
    secure=True
)

# ── WEBSOCKET MANAGER ─────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]

    async def send_to_user(self, user_id: str, data: dict):
        if user_id in self.active_connections:
            try:
                await self.active_connections[user_id].send_text(json.dumps(data))
            except Exception:
                self.disconnect(user_id)

    def is_online(self, user_id: str) -> bool:
        return user_id in self.active_connections


manager = ConnectionManager()


# ── WEBSOCKET ENDPOINT ────────────────────────────────────────
@router.websocket("/ws/{token}")
async def websocket_endpoint(websocket: WebSocket, token: str):
    payload = decode_token(token)
    if not payload:
        await websocket.close(code=4001)
        return

    user_id = payload.get("sub")
    if not user_id:
        await websocket.close(code=4001)
        return

    await manager.connect(user_id, websocket)

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.last_seen = datetime.utcnow()
            db.commit()

            # Broadcast online status
            convs = db.query(Conversation).filter(
                or_(Conversation.user1_id == user_id, Conversation.user2_id == user_id)
            ).all()
            for conv in convs:
                other_id = str(conv.user2_id) if str(conv.user1_id) == user_id else str(conv.user1_id)
                if manager.is_online(other_id):
                    import asyncio
                    asyncio.create_task(manager.send_to_user(other_id, {
                        "type": "user_online",
                        "user_id": user_id,
                        "last_seen": str(user.last_seen)
                    }))

        await websocket.send_text(json.dumps({
            "type": "connected",
            "message": "Connected successfully"
        }))

        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            msg_type = message_data.get("type")

            if msg_type == "send_message":
                receiver_id = message_data.get("receiver_id")
                content = message_data.get("content", "").strip()
                if not content or not receiver_id:
                    continue

                conversation = _get_or_create_conversation(db, user_id, receiver_id)
                sender = db.query(User).filter(User.id == user_id).first()

                msg = Message(
                    conversation_id=conversation.id,
                    sender_id=user_id,
                    content=content
                )
                db.add(msg)
                conversation.updated_at = datetime.utcnow()

                # DB Notification
                notif = Notification(
                    user_id=receiver_id,
                    type=NotifType.message,
                    message=f"{sender.full_name}: {content[:50]}"
                )
                db.add(notif)
                db.commit()

                # FCM Push — sirf agar offline ho
                receiver = db.query(User).filter(User.id == receiver_id).first()
                if receiver and receiver.fcm_token and not manager.is_online(receiver_id):
                    send_push_notification(
                        fcm_token=receiver.fcm_token,
                        title=sender.full_name,
                        body=content[:100],
                        data={
                            "type": "message",
                            "sender_id": user_id,
                            "conversation_id": str(conversation.id)
                        }
                    )

                msg_payload = {
                    "type": "new_message",
                    "id": str(msg.id),
                    "conversation_id": str(conversation.id),
                    "sender_id": user_id,
                    "content": content,
                    "is_seen": False,
                    "created_at": str(msg.created_at)
                }
                await manager.send_to_user(receiver_id, msg_payload)
                # Sender already adds via REST internally, DO NOT broadcast back to sender to prevent duplicates

            elif msg_type == "seen":
                message_id = message_data.get("message_id")
                if message_id:
                    msg = db.query(Message).filter(Message.id == message_id).first()
                    if msg and str(msg.sender_id) != user_id:
                        msg.is_seen = True
                        msg.seen_at = datetime.utcnow()
                        db.commit()
                        await manager.send_to_user(
                            str(msg.sender_id),
                            {"type": "message_seen", "message_id": message_id}
                        )

            elif msg_type in ["typing", "stop_typing", "recording", "stop_recording"]:
                conv_id = message_data.get("conversation_id")
                if conv_id:
                    conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
                    if conv:
                        other_id = str(conv.user2_id) if str(conv.user1_id) == user_id else str(conv.user1_id)
                        payload = {
                            "type": msg_type,
                            "user_id": user_id,
                            "conversation_id": conv_id
                        }
                        if msg_type == "typing":
                            payload["is_typing"] = message_data.get("is_typing", True)
                        
                        await manager.send_to_user(other_id, payload)

            elif msg_type == "join_conversation":
                conv_id = message_data.get("conversation_id")
                if conv_id:
                    conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
                    if conv:
                        other_id = str(conv.user2_id) if str(conv.user1_id) == user_id else str(conv.user1_id)
                        await manager.send_to_user(other_id, {
                            "type": "user_in_chat",
                            "user_id": user_id,
                            "conversation_id": conv_id
                        })

            elif msg_type == "leave_conversation":
                conv_id = message_data.get("conversation_id")
                if conv_id:
                    conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
                    if conv:
                        other_id = str(conv.user2_id) if str(conv.user1_id) == user_id else str(conv.user1_id)
                        await manager.send_to_user(other_id, {
                            "type": "user_left_chat",
                            "user_id": user_id
                        })

            elif msg_type == "delete_message":
                message_id = message_data.get("message_id")
                for_everyone = message_data.get("for_everyone", False)
                if message_id:
                    msg = db.query(Message).filter(Message.id == message_id).first()
                    if msg and str(msg.sender_id) == user_id:
                        conv = db.query(Conversation).filter(Conversation.id == msg.conversation_id).first()
                        other_id = str(conv.user2_id) if str(conv.user1_id) == user_id else str(conv.user1_id)
                        if for_everyone:
                            msg.content = "__deleted__"
                            msg.media_url = None
                            db.commit()
                            await manager.send_to_user(other_id, {
                                "type": "message_deleted",
                                "message_id": message_id,
                                "for_everyone": True
                            })
                        else:
                            db.delete(msg)
                            db.commit()

            elif msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect:
        manager.disconnect(user_id)
        db_update = SessionLocal()
        try:
            u = db_update.query(User).filter(User.id == user_id).first()
            if u:
                u.last_seen = datetime.utcnow()
                db_update.commit()
                
                # Broadcast offline status
                convs = db_update.query(Conversation).filter(
                    or_(Conversation.user1_id == user_id, Conversation.user2_id == user_id)
                ).all()
                for conv in convs:
                    other_id = str(conv.user2_id) if str(conv.user1_id) == user_id else str(conv.user1_id)
                    if manager.is_online(other_id):
                        import asyncio
                        asyncio.create_task(manager.send_to_user(other_id, {
                            "type": "user_offline",
                            "user_id": user_id,
                            "last_seen": str(u.last_seen)
                        }))
        finally:
            db_update.close()
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(user_id)
    finally:
        db.close()


# ── HELPER: Get or create conversation ───────────────────────
def _get_or_create_conversation(db, user1_id: str, user2_id: str) -> Conversation:
    conversation = db.query(Conversation).filter(
        or_(
            and_(Conversation.user1_id == user1_id, Conversation.user2_id == user2_id),
            and_(Conversation.user1_id == user2_id, Conversation.user2_id == user1_id)
        )
    ).first()
    if not conversation:
        conversation = Conversation(user1_id=user1_id, user2_id=user2_id)
        db.add(conversation)
        db.flush()
    return conversation


# ── GET CONVERSATIONS ─────────────────────────────────────────
@router.get("/conversations")
def get_conversations(
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    conversations = db.query(Conversation).filter(
        or_(
            Conversation.user1_id == current_user.id,
            Conversation.user2_id == current_user.id
        )
    ).order_by(Conversation.updated_at.desc()).all()

    result = []
    for conv in conversations:
        other_id = (
            conv.user2_id
            if str(conv.user1_id) == str(current_user.id)
            else conv.user1_id
        )
        other_user = db.query(User).filter(User.id == other_id).first()
        if not other_user:
            continue

        other_profile = db.query(Profile).filter(Profile.user_id == other_id).first()
        last_msg = db.query(Message).filter(
            Message.conversation_id == conv.id
        ).order_by(Message.created_at.desc()).first()

        unread_count = db.query(Message).filter(
            Message.conversation_id == conv.id,
            Message.sender_id == other_id,
            Message.is_seen == False
        ).count()

        # Last message display text
        last_msg_text = None
        if last_msg:
            if last_msg.content and last_msg.content != "__deleted__":
                last_msg_text = last_msg.content
            elif last_msg.media_type == 'image':
                last_msg_text = '📷 Image'
            elif last_msg.media_type == 'video':
                last_msg_text = '🎥 Video'
            elif last_msg.media_type == 'audio':
                last_msg_text = '🎤 Voice message'
            elif last_msg.content == "__deleted__":
                last_msg_text = 'Message deleted'

        result.append({
            "id": str(conv.id),
            "other_user_id": str(other_id),
            "other_user_name": other_user.full_name,
            "other_user_photo": other_profile.profile_photo if other_profile else None,
            "is_online": manager.is_online(str(other_id)),
            "last_seen": str(other_user.last_seen),
            "last_message": last_msg_text,
            "last_message_time": str(last_msg.created_at) if last_msg else None,
            "unread_count": unread_count
        })

    return result


# ── GET MESSAGES ──────────────────────────────────────────────
@router.get("/messages/{conversation_id}")
def get_messages(
    conversation_id: str,
    page: int = 1,
    limit: int = 50,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        or_(
            Conversation.user1_id == current_user.id,
            Conversation.user2_id == current_user.id
        )
    ).first()

    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    messages = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(Message.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    # Mark as seen
    db.query(Message).filter(
        Message.conversation_id == conversation_id,
        Message.sender_id != current_user.id,
        Message.is_seen == False
    ).update({"is_seen": True, "seen_at": datetime.utcnow()})
    db.commit()

    return [
        {
            "id": str(m.id),
            "conversation_id": str(m.conversation_id),
            "sender_id": str(m.sender_id),
            "content": m.content,
            "media_url": m.media_url,
            "media_type": m.media_type,
            "media_thumbnail": m.media_thumbnail,
            "is_seen": m.is_seen,
            "seen_at": str(m.seen_at) if m.seen_at else None,
            "created_at": str(m.created_at)
        }
        for m in reversed(messages)
    ]


# ── DELETE CONVERSATION ───────────────────────────────────────
@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        or_(
            Conversation.user1_id == current_user.id,
            Conversation.user2_id == current_user.id
        )
    ).first()

    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    db.query(Message).filter(Message.conversation_id == conversation_id).delete()
    db.delete(conversation)
    db.commit()
    return {"message": "Conversation deleted"}


# ── SEND MESSAGE REST fallback ────────────────────────────────
@router.post("/send")
def send_message(
    request: SendMessageRequest,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    conversation = _get_or_create_conversation(db, str(current_user.id), request.receiver_id)

    msg = Message(
        conversation_id=conversation.id,
        sender_id=current_user.id,
        content=request.content
    )
    db.add(msg)
    conversation.updated_at = datetime.utcnow()

    notif = Notification(
        user_id=request.receiver_id,
        type=NotifType.message,
        message=f"{current_user.full_name}: {request.content[:50]}"
    )
    db.add(notif)
    db.commit()

    receiver = db.query(User).filter(User.id == request.receiver_id).first()
    if receiver and receiver.fcm_token:
        send_push_notification(
            fcm_token=receiver.fcm_token,
            title=current_user.full_name,
            body=request.content[:100],
            data={
                "type": "message",
                "sender_id": str(current_user.id),
                "conversation_id": str(conversation.id)
            }
        )

    return {
        "id": str(msg.id),
        "conversation_id": str(conversation.id),
        "sender_id": str(current_user.id),
        "content": msg.content,
        "media_url": None,
        "media_type": None,
        "is_seen": False,
        "created_at": str(msg.created_at)
    }


# ── SEND MEDIA — image / video / audio ───────────────────────
@router.post("/send-media")
async def send_media(
    receiver_id: str = Form(...),
    media_type: str = Form(...),   # 'image' | 'video' | 'audio'
    file: UploadFile = File(...),
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    # Validate type
    allowed_types = {
        'image': ['image/jpeg', 'image/png', 'image/jpg', 'image/webp', 'image/gif'],
        'video': ['video/mp4', 'video/quicktime', 'video/3gpp', 'video/x-msvideo'],
        'audio': ['audio/mpeg', 'audio/mp4', 'audio/aac', 'audio/wav',
                  'audio/ogg', 'audio/webm', 'audio/x-m4a', 'application/octet-stream'],
    }

    if media_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Invalid media_type. Use image, video, or audio")

    # Upload to Cloudinary
    try:
        contents = await file.read()

        # Cloudinary resource type
        resource_type_map = {'image': 'image', 'video': 'video', 'audio': 'video'}
        resource_type = resource_type_map[media_type]

        # Folder by type
        folder_map = {'image': 'robina_chat_images', 'video': 'robina_chat_videos', 'audio': 'robina_chat_audio'}
        folder = folder_map[media_type]

        upload_options = {
            'folder': folder,
            'resource_type': resource_type,
        }

        # Image compression
        if media_type == 'image':
            upload_options['transformation'] = [
                {'width': 1200, 'height': 1200, 'crop': 'limit'},
                {'quality': 'auto:good'},
                {'fetch_format': 'auto'}
            ]

        result = cloudinary.uploader.upload(contents, **upload_options)
        media_url = result['secure_url']

        # Video thumbnail
        media_thumbnail = None
        if media_type == 'video':
            media_thumbnail = result.get('secure_url', '').replace(
                '/upload/', '/upload/so_0,w_400,h_400,c_fill/'
            ).replace('.mp4', '.jpg').replace('.mov', '.jpg')

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Media upload failed: {str(e)}")

    # Save message
    conversation = _get_or_create_conversation(db, str(current_user.id), receiver_id)

    # Content = emoji label for display in conversation list
    content_label = {'image': '📷 Image', 'video': '🎥 Video', 'audio': '🎤 Voice message'}

    msg = Message(
        conversation_id=conversation.id,
        sender_id=current_user.id,
        content=content_label[media_type],
        media_url=media_url,
        media_type=media_type,
        media_thumbnail=media_thumbnail
    )
    db.add(msg)
    conversation.updated_at = datetime.utcnow()

    # Notification
    notif_body = {'image': 'sent a photo', 'video': 'sent a video', 'audio': 'sent a voice message'}
    notif = Notification(
        user_id=receiver_id,
        type=NotifType.message,
        message=f"{current_user.full_name} {notif_body[media_type]}"
    )
    db.add(notif)
    db.commit()

    # FCM push
    receiver = db.query(User).filter(User.id == receiver_id).first()
    if receiver and receiver.fcm_token:
        push_body = {'image': '📷 Photo', 'video': '🎥 Video', 'audio': '🎤 Voice message'}
        send_push_notification(
            fcm_token=receiver.fcm_token,
            title=current_user.full_name,
            body=push_body[media_type],
            data={
                "type": "message",
                "sender_id": str(current_user.id),
                "conversation_id": str(conversation.id),
                "media_type": media_type
            }
        )

    # Send via WebSocket to receiver if online
    msg_payload = {
        "type": "new_message",
        "id": str(msg.id),
        "conversation_id": str(conversation.id),
        "sender_id": str(current_user.id),
        "content": content_label[media_type],
        "media_url": media_url,
        "media_type": media_type,
        "media_thumbnail": media_thumbnail,
        "is_seen": False,
        "created_at": str(msg.created_at)
    }
    await manager.send_to_user(receiver_id, msg_payload)

    return {
        "id": str(msg.id),
        "conversation_id": str(conversation.id),
        "sender_id": str(current_user.id),
        "content": content_label[media_type],
        "media_url": media_url,
        "media_type": media_type,
        "media_thumbnail": media_thumbnail,
        "is_seen": False,
        "created_at": str(msg.created_at)
    }


# ── USER ONLINE STATUS ────────────────────────────────────────
@router.get("/status/{user_id}")
def get_user_status(
    user_id: str,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "is_online": manager.is_online(user_id),
        "last_seen": str(user.last_seen) if user.last_seen else None
    }