from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
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
from datetime import datetime
from typing import Dict, List
import json

router = APIRouter(prefix="/chat", tags=["Chat"])

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
                await self.active_connections[user_id].send_text(
                    json.dumps(data)
                )
            except Exception:
                self.disconnect(user_id)

    def is_online(self, user_id: str) -> bool:
        return user_id in self.active_connections

manager = ConnectionManager()

# ── WEBSOCKET ENDPOINT ────────────────────────────────────────
@router.websocket("/ws/{token}")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str
):
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
        # Update last seen
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.last_seen = datetime.utcnow()
            db.commit()

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

                # Get or create conversation
                conversation = db.query(Conversation).filter(
                    or_(
                        and_(
                            Conversation.user1_id == user_id,
                            Conversation.user2_id == receiver_id
                        ),
                        and_(
                            Conversation.user1_id == receiver_id,
                            Conversation.user2_id == user_id
                        )
                    )
                ).first()

                if not conversation:
                    conversation = Conversation(
                        user1_id=user_id,
                        user2_id=receiver_id
                    )
                    db.add(conversation)
                    db.flush()

                # Save message
                msg = Message(
                    conversation_id=conversation.id,
                    sender_id=user_id,
                    content=content
                )
                db.add(msg)
                conversation.updated_at = datetime.utcnow()

                # Notification
                sender = db.query(User).filter(
                    User.id == user_id
                ).first()
                notif = Notification(
                    user_id=receiver_id,
                    type=NotifType.message,
                    message=f"{sender.full_name}: {content[:50]}"
                )
                db.add(notif)
                db.commit()

                msg_payload = {
                    "type": "new_message",
                    "id": str(msg.id),
                    "conversation_id": str(conversation.id),
                    "sender_id": user_id,
                    "content": content,
                    "is_seen": False,
                    "created_at": str(msg.created_at)
                }

                # Send to receiver if online
                await manager.send_to_user(receiver_id, msg_payload)
                # Send back to sender
                await manager.send_to_user(user_id, msg_payload)

            elif msg_type == "seen":
                message_id = message_data.get("message_id")
                if message_id:
                    msg = db.query(Message).filter(
                        Message.id == message_id
                    ).first()
                    if msg and str(msg.sender_id) != user_id:
                        msg.is_seen = True
                        msg.seen_at = datetime.utcnow()
                        db.commit()

                        await manager.send_to_user(
                            str(msg.sender_id),
                            {
                                "type": "message_seen",
                                "message_id": message_id
                            }
                        )

            elif msg_type == "typing":
                receiver_id = message_data.get("receiver_id")
                if receiver_id:
                    await manager.send_to_user(
                        receiver_id,
                        {
                            "type": "typing",
                            "sender_id": user_id,
                            "is_typing": message_data.get("is_typing", True)
                        }
                    )

            elif msg_type == "ping":
                await websocket.send_text(json.dumps({
                    "type": "pong"
                }))

    except WebSocketDisconnect:
        manager.disconnect(user_id)
        db_update = SessionLocal()
        try:
            u = db_update.query(User).filter(User.id == user_id).first()
            if u:
                u.last_seen = datetime.utcnow()
                db_update.commit()
        finally:
            db_update.close()
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(user_id)
    finally:
        db.close()

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

        other_user = db.query(User).filter(
            User.id == other_id
        ).first()

        if not other_user:
            continue

        other_profile = db.query(Profile).filter(
            Profile.user_id == other_id
        ).first()

        last_msg = db.query(Message).filter(
            Message.conversation_id == conv.id
        ).order_by(Message.created_at.desc()).first()

        unread_count = db.query(Message).filter(
            Message.conversation_id == conv.id,
            Message.sender_id == other_id,
            Message.is_seen == False
        ).count()

        result.append({
            "id": str(conv.id),
            "other_user_id": str(other_id),
            "other_user_name": other_user.full_name,
            "other_user_photo": (
                other_profile.profile_photo
                if other_profile else None
            ),
            "is_online": manager.is_online(str(other_id)),
            "last_seen": str(other_user.last_seen),
            "last_message": last_msg.content if last_msg else None,
            "last_message_time": (
                str(last_msg.created_at) if last_msg else None
            ),
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    messages = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(
        Message.created_at.desc()
    ).offset((page - 1) * limit).limit(limit).all()

    # Mark as seen
    db.query(Message).filter(
        Message.conversation_id == conversation_id,
        Message.sender_id != current_user.id,
        Message.is_seen == False
    ).update({
        "is_seen": True,
        "seen_at": datetime.utcnow()
    })
    db.commit()

    return [
        {
            "id": str(m.id),
            "conversation_id": str(m.conversation_id),
            "sender_id": str(m.sender_id),
            "content": m.content,
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).delete()
    db.delete(conversation)
    db.commit()

    return {"message": "Conversation deleted"}

# ── SEND MESSAGE (REST fallback) ──────────────────────────────
@router.post("/send")
def send_message(
    request: SendMessageRequest,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    conversation = db.query(Conversation).filter(
        or_(
            and_(
                Conversation.user1_id == current_user.id,
                Conversation.user2_id == request.receiver_id
            ),
            and_(
                Conversation.user1_id == request.receiver_id,
                Conversation.user2_id == current_user.id
            )
        )
    ).first()

    if not conversation:
        conversation = Conversation(
            user1_id=current_user.id,
            user2_id=request.receiver_id
        )
        db.add(conversation)
        db.flush()

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

    return {
        "id": str(msg.id),
        "conversation_id": str(conversation.id),
        "sender_id": str(current_user.id),
        "content": msg.content,
        "is_seen": False,
        "created_at": str(msg.created_at)
    }