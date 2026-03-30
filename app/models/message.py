import enum
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base
import uuid
from datetime import datetime


class MessageStatus(enum.Enum):
    sent = "sent"
    delivered = "delivered"
    seen = "seen"


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user1_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    user2_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = relationship("Message", back_populates="conversation")


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"))
    sender_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))

    # Text message
    content = Column(Text, nullable=True)

    # Media fields — image / video / audio
    media_url = Column(String, nullable=True)       # Cloudinary URL
    media_type = Column(String, nullable=True)      # 'image' | 'video' | 'audio'
    media_thumbnail = Column(String, nullable=True) # Video thumbnail URL

    # Quote fields
    quote_content = Column(Text, nullable=True)
    quote_sender = Column(String, nullable=True)

    # Delete for me functionality
    deleted_by = Column(String, default="")

    status = Column(Enum(MessageStatus, native_enum=False, length=50), default=MessageStatus.sent)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")
    sender = relationship("User", foreign_keys=[sender_id], back_populates="sent_messages")