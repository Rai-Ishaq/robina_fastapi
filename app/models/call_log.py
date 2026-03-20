# app/models/call_log.py
import uuid
from sqlalchemy import Column, String, DateTime, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import enum
from app.database import Base

class CallType(str, enum.Enum):
    audio = "audio"
    video = "video"

class CallStatus(str, enum.Enum):
    missed = "missed"
    completed = "completed"
    declined = "declined"

class CallLog(Base):
    __tablename__ = "call_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    caller_id = Column(UUID(as_uuid=True), nullable=False)
    receiver_id = Column(UUID(as_uuid=True), nullable=False)
    channel_name = Column(String, nullable=False)
    call_type = Column(SQLEnum(CallType), default=CallType.audio)
    status = Column(SQLEnum(CallStatus), default=CallStatus.missed)
    duration_seconds = Column(String, default="0")
    created_at = Column(DateTime, default=datetime.utcnow)