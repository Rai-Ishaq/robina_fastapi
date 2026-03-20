from sqlalchemy import Column, String, Integer, Float, Date, Boolean, DateTime, Text, ForeignKey, ARRAY
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base
import uuid
from datetime import datetime

class Profile(Base):
    __tablename__ = "profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True)

    # Step 1 - Personal
    date_of_birth = Column(Date, nullable=True)
    height_cm = Column(Integer, nullable=True)
    weight_kg = Column(Integer, nullable=True)
    marital_status = Column(String(50), nullable=True)
    caste = Column(String(100), nullable=True)
    mother_tongue = Column(String(100), nullable=True)

    # Step 2 - Residence
    house_ownership = Column(String(100), nullable=True)
    house_size = Column(String(100), nullable=True)
    country = Column(String(100), nullable=True)
    city = Column(String(100), nullable=True)

    # Step 3 - Religion & Family
    religion = Column(String(50), default="Islam")
    sect = Column(String(100), nullable=True)
    family_status = Column(String(100), nullable=True)
    family_values = Column(String(100), nullable=True)
    siblings_count = Column(String(50), nullable=True)

    # Step 4 - Education & Career
    education = Column(String(100), nullable=True)
    institution_name = Column(String(200), nullable=True)
    profession = Column(String(200), nullable=True)
    employment_status = Column(String(100), nullable=True)
    annual_income = Column(String(100), nullable=True)

    # Step 5 - Lifestyle
    dietary_preference = Column(String(100), nullable=True)
    exercise_habits = Column(String(100), nullable=True)
    smoking = Column(String(50), nullable=True)
    living_style = Column(String(100), nullable=True)
    profile_photo = Column(String(500), nullable=True)

    # Step 6 - Partner Preferences
    pref_age_min = Column(Integer, default=18)
    pref_age_max = Column(Integer, default=35)
    pref_caste = Column(ARRAY(String), nullable=True)
    pref_education = Column(String(100), nullable=True)
    pref_city = Column(String(100), nullable=True)
    pref_marital_status = Column(String(100), nullable=True)
    pref_family_status = Column(String(100), nullable=True)

    # Meta
    setup_step = Column(Integer, default=0)
    profile_views = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="profile")