from sqlalchemy import Column, String, Boolean, DateTime, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base
import uuid
from datetime import datetime

class PremiumPlan(Base):
    __tablename__ = "premium_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    duration_months = Column(Integer, nullable=False)
    price_pkr = Column(Integer, nullable=False)
    price_per_month = Column(Integer, nullable=False)
    savings_percent = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class UserSubscription(Base):
    __tablename__ = "user_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    plan_id = Column(UUID(as_uuid=True), ForeignKey("premium_plans.id"))
    status = Column(String(50), default="active")
    starts_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    payment_method = Column(String(100), nullable=True)
    transaction_id = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", foreign_keys=[user_id])
    plan = relationship("PremiumPlan", foreign_keys=[plan_id])