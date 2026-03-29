import json
import cloudinary
import cloudinary.uploader
import os
from typing import Dict
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, desc
from app.database import get_db
from app.models.user import User
from app.models.chat import Conversation, Message, MessageStatus
from app.utils.helpers import get_verified_user, get_current_user
from app.core.security import decode_token
from app.services.firebase import send_push_notification

router = APIRouter(prefix="/chat", tags=["Chat"])

cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME", ""),
    api_key=os.environ.get("CLOUDINARY_API_KEY", ""),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET", ""),
)


class ConnectionManager:
    def __init__(self):
        self.connections: Dict[str, WebSocket] = {}

    async def connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        self.connections[user_id] = ws

    def disconnect(self, user_id: str):
        self.connections.pop(user_id, None)

    def is_online(self, user_id: str) -> bool:
        return user_id in self.connections

    async def send_to(self, user_id: str, data: dict):
        ws = self.connections.get(user_id)
        if ws:
            try:
                await ws.send_text(json.dumps(data))
            except Exception:
                self.connections.pop(user_id, None)


manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str = Query(...), db: Session = Depends(get_db)):
    payload = decode_token(token)
    if not payload:
        await ws.close(code=4001)
        return

    user_id = payload.get("sub")
    if not user_id:
        await ws.close(code=4001)
        return

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        await ws.close(code=4001)
        return

    await manager.connect(str(user_id), ws)

    user.is_online = True
    user.last_seen = None
    db.commit()

    conversations = db.query(Conversation).filter(
        or_(Conversation.user1_id == user_id, Conversation.user2_id == user_id)
    ).all()

    for conv in conversations:
        other_id = str(conv.user2_id if str(conv.user1_id) == str(user_id) else conv.user1_id)
        await manager.send_to(other_id, {
            "type": "user_online",
            "user_id": str(user_id),
        })

    try:
        while True:
            text = await ws.receive_text()
            try:
                msg = json.loads(text)
            except Exception:
                continue

            mtype = msg.get("type", "")

            if mtype == "ping":
                await manager.send_to(str(user_id), {"type": "pong"})

            elif mtype == "send_message":
                receiver_id = msg.get("receiver_id", "")
                content = msg.get("content", "").strip()
                conv_id = msg.get("conversation_id", "")

                if not content or not receiver_id:
                    continue

                receiver = db.query(User).filter(User.id == receiver_id).first()
                if not receiver:
                    continue

                conv = None
                if conv_id:
                    conv = db.query(Conversation).filter(Conversation.id == conv_id).first()

                if not conv:
                    conv = db.query(Conversation).filter(
                        or_(
                            and_(Conversation.user1_id == user_id, Conversation.user2_id == receiver_id),
                            and_(Conversation.user1_id == receiver_id, Conversation.user2_id == user_id),
                        )
                    ).first()

                if not conv:
                    from uuid import uuid4
                    conv = Conversation(id=uuid4(), user1_id=user_id, user2_id=receiver_id)
                    db.add(conv)
                    db.flush()

                status = MessageStatus.seen if manager.is_online(receiver_id) else MessageStatus.sent
                new_msg = Message(
                    conversation_id=conv.id,
                    sender_id=user_id,
                    content=content,
                    status=status,
                    quote_content=msg.get("quote_content"),
                    quote_sender=msg.get("quote_sender"),
                )
                db.add(new_msg)
                db.commit()
                db.refresh(new_msg)

                payload_out = {
                    "type": "new_message",
                    "id": str(new_msg.id),
                    "conversation_id": str(conv.id),
                    "sender_id": str(user_id),
                    "receiver_id": str(receiver_id),
                    "content": content,
                    "created_at": new_msg.created_at.isoformat(),
                    "status": new_msg.status.value,
                    "quote_content": msg.get("quote_content"),
                    "quote_sender": msg.get("quote_sender"),
                }

                await manager.send_to(str(user_id), payload_out)
                await manager.send_to(str(receiver_id), payload_out)

                if not manager.is_online(str(receiver_id)) and receiver.fcm_token:
                    send_push_notification(
                        fcm_token=receiver.fcm_token,
                        title=user.full_name or "New Message",
                        body=content[:100],
                        data={
                            "type": "chat_message",
                            "sender_id": str(user_id),
                            "conversation_id": str(conv.id),
                        }
                    )

            elif mtype == "messages_seen":
                conv_id = msg.get("conversation_id", "")
                if not conv_id:
                    continue

                msgs_to_update = db.query(Message).filter(
                    Message.conversation_id == conv_id,
                    Message.sender_id != user_id,
                    Message.status != MessageStatus.seen,
                ).all()

                for m in msgs_to_update:
                    m.status = MessageStatus.seen
                db.commit()

                conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
                if conv:
                    other_id = str(conv.user2_id if str(conv.user1_id) == str(user_id) else conv.user1_id)
                    await manager.send_to(other_id, {
                        "type": "messages_seen",
                        "conversation_id": conv_id,
                        "seen_by": str(user_id),
                    })

            elif mtype in ("typing", "stop_typing", "recording", "stop_recording"):
                conv_id = msg.get("conversation_id", "")
                conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
                if conv:
                    other_id = str(conv.user2_id if str(conv.user1_id) == str(user_id) else conv.user1_id)
                    await manager.send_to(other_id, {
                        "type": mtype,
                        "conversation_id": conv_id,
                        "user_id": str(user_id),
                    })

            elif mtype == "delete_message":
                message_id = msg.get("message_id", "")
                for_everyone = msg.get("for_everyone", False)
                db_msg = db.query(Message).filter(
                    Message.id == message_id,
                    Message.sender_id == user_id,
                ).first()
                if db_msg:
                    if for_everyone:
                        db_msg.content = "__deleted__"
                        db.commit()
                        conv = db.query(Conversation).filter(Conversation.id == db_msg.conversation_id).first()
                        if conv:
                            other_id = str(conv.user2_id if str(conv.user1_id) == str(user_id) else conv.user1_id)
                            await manager.send_to(other_id, {
                                "type": "message_deleted",
                                "message_id": message_id,
                                "for_everyone": True,
                            })
                    else:
                        db.delete(db_msg)
                        db.commit()

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(str(user_id))
        from datetime import datetime
        user.is_online = False
        user.last_seen = datetime.utcnow()
        db.commit()

        for conv in conversations:
            other_id = str(conv.user2_id if str(conv.user1_id) == str(user_id) else conv.user1_id)
            await manager.send_to(other_id, {
                "type": "user_offline",
                "user_id": str(user_id),
                "last_seen": user.last_seen.isoformat(),
            })


@router.get("/conversations")
def get_conversations(current_user: User = Depends(get_verified_user), db: Session = Depends(get_db)):
    convs = db.query(Conversation).filter(
        or_(Conversation.user1_id == current_user.id, Conversation.user2_id == current_user.id)
    ).order_by(desc(Conversation.updated_at)).all()

    result = []
    for conv in convs:
        other_id = conv.user2_id if str(conv.user1_id) == str(current_user.id) else conv.user1_id
        other = db.query(User).filter(User.id == other_id).first()
        if not other:
            continue

        last_msg = db.query(Message).filter(
            Message.conversation_id == conv.id
        ).order_by(desc(Message.created_at)).first()

        unread_count = db.query(Message).filter(
            Message.conversation_id == conv.id,
            Message.sender_id != current_user.id,
            Message.status != MessageStatus.seen,
        ).count()

        from app.models.profile import Profile
        profile = db.query(Profile).filter(Profile.user_id == other_id).first()
        photo = profile.profile_photo if profile else None

        result.append({
            "id": str(conv.id),
            "other_user_id": str(other_id),
            "other_user_name": other.full_name or "User",
            "other_user_photo": photo,
            "last_message": last_msg.content if last_msg else "",
            "last_message_time": last_msg.created_at.isoformat() if last_msg else conv.created_at.isoformat(),
            "unread_count": unread_count,
            "is_online": manager.is_online(str(other_id)),
            "last_seen": other.last_seen.isoformat() if other.last_seen else None,
            "updated_at": conv.updated_at.isoformat() if conv.updated_at else conv.created_at.isoformat(),
        })
    return result


@router.get("/messages/{conversation_id}")
def get_messages(
    conversation_id: str,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        return []

    if str(conv.user1_id) != str(current_user.id) and str(conv.user2_id) != str(current_user.id):
        return []

    msgs = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(Message.created_at).all()

    return [
        {
            "id": str(m.id),
            "conversation_id": str(m.conversation_id),
            "sender_id": str(m.sender_id),
            "content": m.content or "",
            "media_url": m.media_url,
            "media_type": m.media_type,
            "media_thumbnail": m.media_thumbnail,
            "status": m.status.value if m.status else "sent",
            "is_seen": m.status == MessageStatus.seen,
            "is_delivered": m.status in (MessageStatus.delivered, MessageStatus.seen),
            "created_at": m.created_at.isoformat(),
            "quote_content": m.quote_content,
            "quote_sender": m.quote_sender,
        }
        for m in msgs
    ]


@router.post("/send")
def send_message_rest(
    body: dict,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    receiver_id = body.get("receiver_id", "")
    content = (body.get("content") or "").strip()
    conv_id = body.get("conversation_id", "")

    if not content or not receiver_id:
        return {"success": False, "error": "Missing fields"}

    receiver = db.query(User).filter(User.id == receiver_id).first()
    if not receiver:
        return {"success": False, "error": "Receiver not found"}

    conv = None
    if conv_id:
        conv = db.query(Conversation).filter(Conversation.id == conv_id).first()

    if not conv:
        conv = db.query(Conversation).filter(
            or_(
                and_(Conversation.user1_id == current_user.id, Conversation.user2_id == receiver_id),
                and_(Conversation.user1_id == receiver_id, Conversation.user2_id == current_user.id),
            )
        ).first()

    if not conv:
        from uuid import uuid4
        conv = Conversation(id=uuid4(), user1_id=current_user.id, user2_id=receiver_id)
        db.add(conv)
        db.flush()

    status = MessageStatus.seen if manager.is_online(str(receiver_id)) else MessageStatus.sent
    new_msg = Message(
        conversation_id=conv.id,
        sender_id=current_user.id,
        content=content,
        status=status,
        quote_content=body.get("quote_content"),
        quote_sender=body.get("quote_sender"),
    )
    db.add(new_msg)
    db.commit()
    db.refresh(new_msg)

    payload_out = {
        "type": "new_message",
        "id": str(new_msg.id),
        "conversation_id": str(conv.id),
        "sender_id": str(current_user.id),
        "receiver_id": str(receiver_id),
        "content": content,
        "created_at": new_msg.created_at.isoformat(),
        "status": new_msg.status.value,
        "quote_content": body.get("quote_content"),
        "quote_sender": body.get("quote_sender"),
    }

    import asyncio
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(manager.send_to(str(receiver_id), payload_out))
        loop.create_task(manager.send_to(str(current_user.id), payload_out))
    except Exception:
        pass

    if not manager.is_online(str(receiver_id)) and receiver.fcm_token:
        send_push_notification(
            fcm_token=receiver.fcm_token,
            title=current_user.full_name or "New Message",
            body=content[:100],
            data={
                "type": "chat_message",
                "sender_id": str(current_user.id),
                "conversation_id": str(conv.id),
            }
        )

    return {
        "success": True,
        "data": {
            "id": str(new_msg.id),
            "conversation_id": str(conv.id),
            "content": content,
            "created_at": new_msg.created_at.isoformat(),
            "status": new_msg.status.value,
        }
    }


@router.post("/send-media")
async def send_media(
    receiver_id: str = Form(...),
    media_type: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    try:
        contents = await file.read()
        resource_type = "video" if media_type in ("video", "audio") else "image"
        upload_result = cloudinary.uploader.upload(
            contents,
            resource_type=resource_type,
            folder="robina_chat",
        )
        media_url = upload_result.get("secure_url", "")
        thumbnail = None
        if media_type == "video":
            thumbnail = upload_result.get("url", "").replace("/upload/", "/upload/w_200,h_200,c_fill/")
    except Exception as e:
        return {"success": False, "error": str(e)}

    receiver = db.query(User).filter(User.id == receiver_id).first()
    if not receiver:
        return {"success": False, "error": "Receiver not found"}

    conv = db.query(Conversation).filter(
        or_(
            and_(Conversation.user1_id == current_user.id, Conversation.user2_id == receiver_id),
            and_(Conversation.user1_id == receiver_id, Conversation.user2_id == current_user.id),
        )
    ).first()

    if not conv:
        from uuid import uuid4
        conv = Conversation(id=uuid4(), user1_id=current_user.id, user2_id=receiver_id)
        db.add(conv)
        db.flush()

    content_text = {"image": "📷 Photo", "video": "🎥 Video", "audio": "🎤 Voice"}.get(media_type, "📎 File")
    status = MessageStatus.seen if manager.is_online(str(receiver_id)) else MessageStatus.sent

    new_msg = Message(
        conversation_id=conv.id,
        sender_id=current_user.id,
        content=content_text,
        media_url=media_url,
        media_type=media_type,
        media_thumbnail=thumbnail,
        status=status,
    )
    db.add(new_msg)
    db.commit()
    db.refresh(new_msg)

    payload_out = {
        "type": "new_message",
        "id": str(new_msg.id),
        "conversation_id": str(conv.id),
        "sender_id": str(current_user.id),
        "receiver_id": str(receiver_id),
        "content": content_text,
        "media_url": media_url,
        "media_type": media_type,
        "media_thumbnail": thumbnail,
        "created_at": new_msg.created_at.isoformat(),
        "status": new_msg.status.value,
    }

    import asyncio
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(manager.send_to(str(receiver_id), payload_out))
        loop.create_task(manager.send_to(str(current_user.id), payload_out))
    except Exception:
        pass

    if not manager.is_online(str(receiver_id)) and receiver.fcm_token:
        send_push_notification(
            fcm_token=receiver.fcm_token,
            title=current_user.full_name or "Message",
            body=content_text,
            data={"type": "chat_message", "sender_id": str(current_user.id), "conversation_id": str(conv.id)},
        )

    return {
        "success": True,
        "data": {
            "id": str(new_msg.id),
            "conversation_id": str(conv.id),
            "media_url": media_url,
            "media_type": media_type,
            "media_thumbnail": thumbnail,
            "content": content_text,
            "created_at": new_msg.created_at.isoformat(),
        }
    }


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if conv and (str(conv.user1_id) == str(current_user.id) or str(conv.user2_id) == str(current_user.id)):
        db.query(Message).filter(Message.conversation_id == conversation_id).delete()
        db.delete(conv)
        db.commit()
    return {"success": True}


@router.get("/status/{user_id}")
def get_user_status(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"is_online": False, "last_seen": None}
    return {
        "is_online": manager.is_online(str(user_id)),
        "last_seen": user.last_seen.isoformat() if user.last_seen else None,
    }