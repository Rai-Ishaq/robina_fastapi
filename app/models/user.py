from sqlalchemy import Column, String, Boolean, DateTime, Enum, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base
import uuid
import enum
from datetime import datetime

class GenderEnum(str, enum.Enum):
    male = "male"
    female = "female"

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    phone = Column(String(20), unique=True, nullable=True)  # ✅ Google users ke liye nullable
    country_code = Column(String(10), default="+92")
    password_hash = Column(String(255), nullable=False)
    gender = Column(Enum(GenderEnum), nullable=True)  # ✅ Google users ke liye nullable
    is_verified = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    is_premium = Column(Boolean, default=False)
    profile_complete = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)
    fcm_token = Column(String(500), nullable=True)
    google_uid = Column(String(128), nullable=True, unique=True)  # ✅ Google Sign In
    user_code = Column(String(20), unique=True, nullable=True)
    date_of_birth = Column(Date, nullable=True)
    verification_status = Column(String(20), default="none")
    verification_doc_url = Column(String(500), nullable=True)
    is_online = Column(Boolean, default=False)

    # Relationships
    profile = relationship("Profile", back_populates="user", uselist=False)
    sent_interests = relationship("Interest", foreign_keys="Interest.sender_id", back_populates="sender")
    received_interests = relationship("Interest", foreign_keys="Interest.receiver_id", back_populates="receiver")
    sent_messages = relationship("Message", foreign_keys="Message.sender_id", back_populates="sender")
    notifications = relationship("Notification", back_populates="user")
    blocked_users = relationship("BlockedUser", foreign_keys="BlockedUser.blocker_id", back_populates="blocker")