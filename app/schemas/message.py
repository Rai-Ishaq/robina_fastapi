from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class SendMessageRequest(BaseModel):
    receiver_id: str
    content: str


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    sender_id: str
    content: Optional[str]
    media_url: Optional[str] = None
    media_type: Optional[str] = None
    media_thumbnail: Optional[str] = None
    is_seen: bool
    created_at: str

    class Config:
        from_attributes = True


class ConversationResponse(BaseModel):
    id: str
    other_user_id: str
    other_user_name: str
    other_user_photo: Optional[str]
    last_message: Optional[str]
    last_message_time: Optional[str]
    unread_count: int

    class Config:
        from_attributes = True