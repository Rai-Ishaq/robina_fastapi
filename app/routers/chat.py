import json
import cloudinary
import cloudinary.uploader
import os
from datetime import datetime
from typing import Dict, Set
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, desc
from app.database import get_db
from app.models.user import User
from app.models.message import Conversation, Message, MessageStatus
from app.models.match import BlockedUser
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
        self.online_users: Set[str] = set()
        self.active_conversations: Dict[str, str] = {}

    async def connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        self.connections[user_id] = ws
        self.online_users.add(user_id)

    def disconnect(self, user_id: str):
        self.connections.pop(user_id, None)
        self.online_users.discard(user_id)
        self.active_conversations.pop(user_id, None)

    def is_online(self, user_id: str) -> bool:
        return user_id in self.online_users

    def get_online_user_ids(self) -> list:
        return list(self.online_users)

    def set_active_conversation(self, user_id: str, conv_id: str):
        self.active_conversations[user_id] = conv_id

    def clear_active_conversation(self, user_id: str):
        self.active_conversations.pop(user_id, None)

    def is_in_conversation(self, user_id: str, conv_id: str) -> bool:
        return self.active_conversations.get(user_id) == conv_id

    async def send_to(self, user_id: str, data: dict):
        ws = self.connections.get(user_id)
        if ws:
            try:
                await ws.send_text(json.dumps(data))
            except Exception:
                self.connections.pop(user_id, None)
                self.online_users.discard(user_id)

    async def broadcast_to_many(self, user_ids: list, data: dict):
        for uid in user_ids:
            await self.send_to(uid, data)


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

    # Get all conversations for this user
    conversations = db.query(Conversation).filter(
        or_(Conversation.user1_id == user_id, Conversation.user2_id == user_id)
    ).all()

    # ✅ Step 1: Notify all partners that THIS user is now online
    for conv in conversations:
        other_id = str(conv.user2_id if str(conv.user1_id) == str(user_id) else conv.user1_id)
        await manager.send_to(other_id, {
            "type": "user_online",
            "user_id": str(user_id),
        })

    # ✅ Step 2: Tell THIS user which of their contacts are already online
    already_online = []
    for conv in conversations:
        other_id = str(conv.user2_id if str(conv.user1_id) == str(user_id) else conv.user1_id)
        if manager.is_online(other_id):
            already_online.append(other_id)

    if already_online:
        await manager.send_to(str(user_id), {
            "type": "online_users_list",
            "user_ids": already_online,
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

            elif mtype == "set_active_conversation":
                conv_id = msg.get("conversation_id", "")
                if conv_id:
                    manager.set_active_conversation(str(user_id), conv_id)
                else:
                    manager.clear_active_conversation(str(user_id))

            elif mtype == "send_message":
                receiver_id = msg.get("receiver_id", "")
                content = msg.get("content", "").strip()
                conv_id = msg.get("conversation_id", "")

                if not content or not receiver_id:
                    continue

                is_blocked = db.query(BlockedUser).filter(
                    or_(
                        and_(BlockedUser.blocker_id == user_id, BlockedUser.blocked_id == receiver_id),
                        and_(BlockedUser.blocker_id == receiver_id, BlockedUser.blocked_id == user_id),
                    )
                ).first()
                if is_blocked:
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

                receiver_online = manager.is_online(str(receiver_id))
                receiver_in_conv = manager.is_in_conversation(str(receiver_id), str(conv.id))

                if receiver_in_conv:
                    status = MessageStatus.seen
                elif receiver_online:
                    status = MessageStatus.delivered
                else:
                    status = MessageStatus.sent

                new_msg = Message(
                    conversation_id=conv.id,
                    sender_id=user_id,
                    content=content,
                    status=status,
                    quote_content=msg.get("quote_content"),
                    quote_sender=msg.get("quote_sender"),
                )
                db.add(new_msg)
                conv.updated_at = datetime.utcnow()
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

                if receiver_in_conv:
                    await manager.send_to(str(user_id), {
                        "type": "messages_seen",
                        "conversation_id": str(conv.id),
                        "seen_by": str(receiver_id),
                    })

                if not receiver_online and receiver.fcm_token:
                    send_push_notification(
                        fcm_token=receiver.fcm_token,
                        title=user.full_name or "New Message",
                        body=content[:100],
                        data={
                            "type": "message",
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

                updated = len(msgs_to_update)
                for m in msgs_to_update:
                    m.status = MessageStatus.seen
                db.commit()

                conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
                if conv and updated > 0:
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
                delete_for_me = msg.get("delete_for_me", False)

                db_msg = db.query(Message).filter(Message.id == message_id).first()
                if db_msg:
                    if for_everyone and str(db_msg.sender_id) == str(user_id):
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
                            await manager.send_to(str(user_id), {
                                "type": "message_deleted",
                                "message_id": message_id,
                                "for_everyone": True,
                            })
                    elif delete_for_me:
                        user_str = str(user_id)
                        current_deleted = db_msg.deleted_by or ""
                        if user_str not in current_deleted:
                            if current_deleted:
                                db_msg.deleted_by = current_deleted + "," + user_str
                            else:
                                db_msg.deleted_by = user_str
                            db.commit()

                        await manager.send_to(str(user_id), {
                            "type": "message_deleted_for_me",
                            "message_id": message_id,
                        })

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(str(user_id))
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

    my_blocks = {str(b.blocked_id) for b in db.query(BlockedUser).filter(BlockedUser.blocker_id == current_user.id).all()}
    blocked_me = {str(b.blocker_id) for b in db.query(BlockedUser).filter(BlockedUser.blocked_id == current_user.id).all()}

    result = []
    for conv in convs:
        other_id = conv.user2_id if str(conv.user1_id) == str(current_user.id) else conv.user1_id
        other = db.query(User).filter(User.id == other_id).first()
        if not other:
            continue

        last_msg = db.query(Message).filter(
            Message.conversation_id == conv.id,
            ~Message.deleted_by.contains(str(current_user.id))
        ).order_by(desc(Message.created_at)).first()

        unread_count = db.query(Message).filter(
            Message.conversation_id == conv.id,
            Message.sender_id != current_user.id,
            Message.status != MessageStatus.seen,
            ~Message.deleted_by.contains(str(current_user.id))
        ).count()

        from app.models.profile import Profile
        profile = db.query(Profile).filter(Profile.user_id == other_id).first()
        photo = profile.profile_photo if profile else None

        other_id_str = str(other_id)
        result.append({
            "id": str(conv.id),
            "other_user_id": other_id_str,
            "other_user_name": other.full_name or "User",
            "other_user_photo": photo,
            "last_message": last_msg.content if last_msg else "",
            "last_message_type": last_msg.media_type if last_msg else None,
            "last_message_time": last_msg.created_at.isoformat() if last_msg else conv.created_at.isoformat(),
            "unread_count": unread_count,
            "is_online": manager.is_online(other_id_str),
            "last_seen": other.last_seen.isoformat() if other.last_seen else None,
            "updated_at": conv.updated_at.isoformat() if conv.updated_at else conv.created_at.isoformat(),
            "blocked_by_me": other_id_str in my_blocks,
            "blocked_by_them": other_id_str in blocked_me,
            "other_user_code": other.user_code or "",
        })
    return result


@router.post("/conversations/{conversation_id}/read")
async def mark_conversation_read(
    conversation_id: str,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        return {"success": False}

    if str(conv.user1_id) != str(current_user.id) and str(conv.user2_id) != str(current_user.id):
        return {"success": False}

    msgs_updated = db.query(Message).filter(
        Message.conversation_id == conversation_id,
        Message.sender_id != current_user.id,
        Message.status != MessageStatus.seen
    ).all()

    updated_count = len(msgs_updated)
    for m in msgs_updated:
        m.status = MessageStatus.seen
    db.commit()

    if updated_count > 0:
        other_id = str(conv.user2_id if str(conv.user1_id) == str(current_user.id) else conv.user1_id)
        import asyncio
        try:
            asyncio.ensure_future(manager.send_to(other_id, {
                "type": "messages_seen",
                "conversation_id": conversation_id,
                "seen_by": str(current_user.id),
            }))
        except Exception:
            pass

    return {"success": True, "updated": updated_count}


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
        Message.conversation_id == conversation_id,
        ~Message.deleted_by.contains(str(current_user.id))
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

    is_blocked = db.query(BlockedUser).filter(
        or_(
            and_(BlockedUser.blocker_id == current_user.id, BlockedUser.blocked_id == receiver_id),
            and_(BlockedUser.blocker_id == receiver_id, BlockedUser.blocked_id == current_user.id),
        )
    ).first()
    if is_blocked:
        return {"success": False, "error": "User is blocked"}

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

    receiver_online = manager.is_online(str(receiver_id))
    receiver_in_conv = manager.is_in_conversation(str(receiver_id), str(conv.id))

    if receiver_in_conv:
        status = MessageStatus.seen
    elif receiver_online:
        status = MessageStatus.delivered
    else:
        status = MessageStatus.sent

    new_msg = Message(
        conversation_id=conv.id,
        sender_id=current_user.id,
        content=content,
        status=status,
        quote_content=body.get("quote_content"),
        quote_sender=body.get("quote_sender"),
    )
    db.add(new_msg)
    conv.updated_at = datetime.utcnow()
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
        loop = asyncio.get_running_loop()
        asyncio.ensure_future(manager.send_to(str(receiver_id), payload_out))
        asyncio.ensure_future(manager.send_to(str(current_user.id), payload_out))
        if receiver_in_conv:
            asyncio.ensure_future(manager.send_to(str(current_user.id), {
                "type": "messages_seen",
                "conversation_id": str(conv.id),
                "seen_by": str(receiver_id),
            }))
    except Exception:
        pass

    if not receiver_online and receiver.fcm_token:
        send_push_notification(
            fcm_token=receiver.fcm_token,
            title=current_user.full_name or "New Message",
            body=content[:100],
            data={
                "type": "message",
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
    quote_content: str = Form(None),
    quote_sender: str = Form(None),
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    is_blocked = db.query(BlockedUser).filter(
        or_(
            and_(BlockedUser.blocker_id == current_user.id, BlockedUser.blocked_id == receiver_id),
            and_(BlockedUser.blocker_id == receiver_id, BlockedUser.blocked_id == current_user.id),
        )
    ).first()
    if is_blocked:
        return {"success": False, "error": "User is blocked"}

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
    receiver_online = manager.is_online(str(receiver_id))
    receiver_in_conv = manager.is_in_conversation(str(receiver_id), str(conv.id))

    if receiver_in_conv:
        status = MessageStatus.seen
    elif receiver_online:
        status = MessageStatus.delivered
    else:
        status = MessageStatus.sent

    new_msg = Message(
        conversation_id=conv.id,
        sender_id=current_user.id,
        content=content_text,
        media_url=media_url,
        media_type=media_type,
        media_thumbnail=thumbnail,
        status=status,
        quote_content=quote_content,
        quote_sender=quote_sender,
    )
    db.add(new_msg)
    conv.updated_at = datetime.utcnow()
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
        loop = asyncio.get_running_loop()
        asyncio.ensure_future(manager.send_to(str(receiver_id), payload_out))
        asyncio.ensure_future(manager.send_to(str(current_user.id), payload_out))
        if receiver_in_conv:
            asyncio.ensure_future(manager.send_to(str(current_user.id), {
                "type": "messages_seen",
                "conversation_id": str(conv.id),
                "seen_by": str(receiver_id),
            }))
    except Exception:
        pass

    if not receiver_online and receiver.fcm_token:
        send_push_notification(
            fcm_token=receiver.fcm_token,
            title=current_user.full_name or "Message",
            body=content_text,
            data={"type": "message", "sender_id": str(current_user.id), "conversation_id": str(conv.id)},
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
            "status": new_msg.status.value,
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
        user_str = str(current_user.id)
        messages = db.query(Message).filter(Message.conversation_id == conversation_id).all()
        for msg in messages:
            current_deleted = msg.deleted_by or ""
            if user_str not in current_deleted:
                if current_deleted:
                    msg.deleted_by = current_deleted + "," + user_str
                else:
                    msg.deleted_by = user_str
        db.commit()
    return {"success": True}


@router.delete("/messages/{conversation_id}/clear")
def clear_chat(
    conversation_id: str,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if conv and (str(conv.user1_id) == str(current_user.id) or str(conv.user2_id) == str(current_user.id)):
        db.query(Message).filter(Message.conversation_id == conversation_id).delete()
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


@router.get("/online-users")
def get_online_users(current_user: User = Depends(get_verified_user)):
    return {"online_user_ids": manager.get_online_user_ids()}


@router.post("/block")
def block_user(
    target_user_id: str,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    existing = db.query(BlockedUser).filter(
        BlockedUser.blocker_id == current_user.id,
        BlockedUser.blocked_id == target_user_id,
    ).first()
    if not existing:
        block = BlockedUser(blocker_id=current_user.id, blocked_id=target_user_id)
        db.add(block)
        db.commit()

    import asyncio
    try:
        loop = asyncio.get_running_loop()
        asyncio.ensure_future(manager.send_to(str(target_user_id), {
            "type": "user_blocked",
            "by_user_id": str(current_user.id),
        }))
    except Exception:
        pass

    return {"success": True}


@router.post("/unblock")
def unblock_user(
    target_user_id: str,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    db.query(BlockedUser).filter(
        BlockedUser.blocker_id == current_user.id,
        BlockedUser.blocked_id == target_user_id,
    ).delete()
    db.commit()

    import asyncio
    try:
        loop = asyncio.get_running_loop()
        asyncio.ensure_future(manager.send_to(str(target_user_id), {
            "type": "user_unblocked",
            "by_user_id": str(current_user.id),
        }))
    except Exception:
        pass

    return {"success": True}


@router.get("/blocked-users")
def get_blocked_users(
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    blocks = db.query(BlockedUser).filter(BlockedUser.blocker_id == current_user.id).all()
    result = []
    for b in blocks:
        other = db.query(User).filter(User.id == b.blocked_id).first()
        if not other:
            continue
        from app.models.profile import Profile
        profile = db.query(Profile).filter(Profile.user_id == b.blocked_id).first()
        result.append({
            "blocked_user_id": str(b.blocked_id),
            "name": other.full_name or "User",
            "photo": profile.profile_photo if profile else None,
            "blocked_at": b.created_at.isoformat(),
        })
    return result


@router.post("/report")
def report_user(
    target_user_id: str,
    reason: str = "Inappropriate behavior",
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    print(f"[REPORT] User {current_user.id} reported {target_user_id}. Reason: {reason}")
    return {"success": True, "message": "Report submitted successfully"}
