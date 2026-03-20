from sqlalchemy import Column, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base
import uuid
from datetime import datetime

class ProfileView(Base):
    __tablename__ = "profile_views"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    viewer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    viewed_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    viewed_at = Column(DateTime, default=datetime.utcnow)

    viewer = relationship("User", foreign_keys=[viewer_id])
    viewed = relationship("User", foreign_keys=[viewed_id])