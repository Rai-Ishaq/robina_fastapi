from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.models.profile import Profile
from app.models.notification import Notification, NotifType
from app.schemas.profile import (
    ProfileStep1, ProfileStep2, ProfileStep3,
    ProfileStep4, ProfileStep5, ProfileStep6,
    ProfileResponse
)
from app.utils.helpers import get_verified_user
from app.core.config import settings
from datetime import datetime, date
import os
import uuid
import shutil
from pydantic import BaseModel

router = APIRouter(prefix="/profile", tags=["Profile"])

def calculate_age(dob: date) -> int:
    today = date.today()
    return today.year - dob.year - (
        (today.month, today.day) < (dob.month, dob.day)
    )

# ── GET MY PROFILE ────────────────────────────────────────────
@router.get("/me")
def get_my_profile(
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    profile = db.query(Profile).filter(
        Profile.user_id == current_user.id
    ).first()

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found"
        )

    age = None
    if profile.date_of_birth:
        age = calculate_age(profile.date_of_birth)

    return {
        "id": str(profile.id),
        "user_id": str(current_user.id),
        "full_name": current_user.full_name,
        "email": current_user.email,
        "gender": current_user.gender,
        "age": age,
        "city": profile.city,
        "country": profile.country,
        "profile_photo": profile.profile_photo,
        "marital_status": profile.marital_status,
        "caste": profile.caste,
        "education": profile.education,
        "profession": profile.profession,
        "setup_step": profile.setup_step,
        "profile_views": profile.profile_views,
        "date_of_birth": str(profile.date_of_birth) if profile.date_of_birth else None,
        "height_cm": profile.height_cm,
        "weight_kg": profile.weight_kg,
        "mother_tongue": profile.mother_tongue,
        "house_ownership": profile.house_ownership,
        "house_size": profile.house_size,
        "religion": profile.religion,
        "sect": profile.sect,
        "family_status": profile.family_status,
        "family_values": profile.family_values,
        "siblings_count": profile.siblings_count,
        "institution_name": profile.institution_name,
        "employment_status": profile.employment_status,
        "annual_income": profile.annual_income,
        "dietary_preference": profile.dietary_preference,
        "exercise_habits": profile.exercise_habits,
        "smoking": profile.smoking,
        "living_style": profile.living_style,
        "pref_age_min": profile.pref_age_min,
        "pref_age_max": profile.pref_age_max,
        "pref_caste": profile.pref_caste,
        "pref_education": profile.pref_education,
        "pref_city": profile.pref_city,
        "pref_marital_status": profile.pref_marital_status,
        "pref_family_status": profile.pref_family_status,
    }

# ── STEP 1 ────────────────────────────────────────────────────
@router.put("/step/1", response_model=dict)
def save_step1(
    data: ProfileStep1,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    profile = db.query(Profile).filter(
        Profile.user_id == current_user.id
    ).first()

    profile.date_of_birth = data.date_of_birth
    profile.height_cm = data.height_cm
    profile.weight_kg = data.weight_kg
    profile.marital_status = data.marital_status
    profile.caste = data.caste
    profile.mother_tongue = data.mother_tongue
    if profile.setup_step < 1:
        profile.setup_step = 1
    profile.updated_at = datetime.utcnow()
    db.commit()

    return {"message": "Step 1 saved", "setup_step": profile.setup_step}

# ── STEP 2 ────────────────────────────────────────────────────
@router.put("/step/2", response_model=dict)
def save_step2(
    data: ProfileStep2,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    profile = db.query(Profile).filter(
        Profile.user_id == current_user.id
    ).first()

    profile.house_ownership = data.house_ownership
    profile.house_size = data.house_size
    profile.country = data.country
    profile.city = data.city
    if profile.setup_step < 2:
        profile.setup_step = 2
    profile.updated_at = datetime.utcnow()
    db.commit()

    return {"message": "Step 2 saved", "setup_step": profile.setup_step}

# ── STEP 3 ────────────────────────────────────────────────────
@router.put("/step/3", response_model=dict)
def save_step3(
    data: ProfileStep3,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    profile = db.query(Profile).filter(
        Profile.user_id == current_user.id
    ).first()

    profile.sect = data.sect
    profile.family_status = data.family_status
    profile.family_values = data.family_values
    profile.siblings_count = data.siblings_count
    if profile.setup_step < 3:
        profile.setup_step = 3
    profile.updated_at = datetime.utcnow()
    db.commit()

    return {"message": "Step 3 saved", "setup_step": profile.setup_step}

# ── STEP 4 ────────────────────────────────────────────────────
@router.put("/step/4", response_model=dict)
def save_step4(
    data: ProfileStep4,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    profile = db.query(Profile).filter(
        Profile.user_id == current_user.id
    ).first()

    profile.education = data.education
    profile.institution_name = data.institution_name
    profile.profession = data.profession
    profile.employment_status = data.employment_status
    profile.annual_income = data.annual_income
    if profile.setup_step < 4:
        profile.setup_step = 4
    profile.updated_at = datetime.utcnow()
    db.commit()

    return {"message": "Step 4 saved", "setup_step": profile.setup_step}

# ── STEP 5 ────────────────────────────────────────────────────
@router.put("/step/5", response_model=dict)
def save_step5(
    data: ProfileStep5,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    profile = db.query(Profile).filter(
        Profile.user_id == current_user.id
    ).first()

    profile.dietary_preference = data.dietary_preference
    profile.exercise_habits = data.exercise_habits
    profile.smoking = data.smoking
    profile.living_style = data.living_style
    if profile.setup_step < 5:
        profile.setup_step = 5
    profile.updated_at = datetime.utcnow()
    db.commit()

    return {"message": "Step 5 saved", "setup_step": profile.setup_step}

# ── UPLOAD PHOTO ──────────────────────────────────────────────
@router.post("/upload-photo", response_model=dict)
def upload_photo(
    file: UploadFile = File(...),
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    allowed = ["image/jpeg", "image/png", "image/jpg"]
    if file.content_type not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only JPEG and PNG images allowed"
        )

    from PIL import Image
    import io

    upload_dir = f"{settings.UPLOAD_DIR}/profiles"
    os.makedirs(upload_dir, exist_ok=True)

    filename = f"{uuid.uuid4()}.jpg"
    filepath = f"{upload_dir}/{filename}"

    # Read and compress
    contents = file.file.read()
    image = Image.open(io.BytesIO(contents))

    # Convert to RGB if needed
    if image.mode in ("RGBA", "P"):
        image = image.convert("RGB")

    # Resize — max 800x800
    max_size = (800, 800)
    image.thumbnail(max_size, Image.LANCZOS)

    # Save compressed
    image.save(filepath, "JPEG", quality=85, optimize=True)

    profile = db.query(Profile).filter(
        Profile.user_id == current_user.id
    ).first()

    # Delete old photo
    if profile.profile_photo:
        old_path = profile.profile_photo.replace(
            settings.BASE_URL + "/", ""
        )
        if os.path.exists(old_path):
            os.remove(old_path)

    photo_url = f"{settings.BASE_URL}/uploads/profiles/{filename}"
    profile.profile_photo = photo_url
    db.commit()

    return {
        "message": "Photo uploaded successfully",
        "photo_url": photo_url
    }

# ── STEP 6 (COMPLETE PROFILE) ─────────────────────────────────
@router.put("/step/6", response_model=dict)
def save_step6(
    data: ProfileStep6,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    profile = db.query(Profile).filter(
        Profile.user_id == current_user.id
    ).first()

    profile.pref_age_min = data.pref_age_min
    profile.pref_age_max = data.pref_age_max
    profile.pref_caste = data.pref_caste
    profile.pref_education = data.pref_education
    profile.pref_city = data.pref_city
    profile.pref_marital_status = data.pref_marital_status
    profile.pref_family_status = data.pref_family_status
    profile.setup_step = 6
    profile.updated_at = datetime.utcnow()

    user = db.query(User).filter(User.id == current_user.id).first()
    user.profile_complete = True
    db.commit()

    return {
        "message": "Profile completed successfully",
        "setup_step": 6,
        "profile_complete": True
    }

# ── UPDATE NAME & TAGLINE ─────────────────────────────────────
# ── UPDATE NAME ───────────────────────────────────────────────


class UpdateBasicRequest(BaseModel):
    full_name: str

@router.put("/update-basic", response_model=dict)
def update_basic(
    data: UpdateBasicRequest,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    current_user.full_name = data.full_name
    db.commit()
    return {"message": "Profile updated successfully"}

# ── VIEW PROFILE (track views) ────────────────────────────────
# ── VIEW PROFILE (track views properly) ──────────────────────
@router.get("/{user_id}")
def get_profile(
    user_id: str,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    from app.models.profile_view import ProfileView
    from datetime import timedelta

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    profile = db.query(Profile).filter(
        Profile.user_id == user_id
    ).first()

    # Track view — avoid duplicate in last 1 hour
    if str(current_user.id) != user_id:
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        recent_view = db.query(ProfileView).filter(
            ProfileView.viewer_id == current_user.id,
            ProfileView.viewed_id == user_id,
            ProfileView.viewed_at >= one_hour_ago
        ).first()

        if not recent_view:
            view = ProfileView(
                viewer_id=current_user.id,
                viewed_id=user_id
            )
            db.add(view)
            if profile:
                profile.profile_views += 1

            notif = Notification(
                user_id=user.id,
                type=NotifType.profile_view,
                message=f"{current_user.full_name} viewed your profile"
            )
            db.add(notif)
            db.commit()

    age = None
    if profile and profile.date_of_birth:
        age = calculate_age(profile.date_of_birth)

    return {
        "id": str(user.id),
        "full_name": user.full_name,
        "gender": user.gender,
        "age": age,
        "city": profile.city if profile else None,
        "country": profile.country if profile else None,
        "profile_photo": profile.profile_photo if profile else None,
        "marital_status": profile.marital_status if profile else None,
        "caste": profile.caste if profile else None,
        "education": profile.education if profile else None,
        "profession": profile.profession if profile else None,
        "height_cm": profile.height_cm if profile else None,
        "religion": profile.religion if profile else "Islam",
        "sect": profile.sect if profile else None,
        "family_status": profile.family_status if profile else None,
        "family_values": profile.family_values if profile else None,
        "employment_status": profile.employment_status if profile else None,
        "dietary_preference": profile.dietary_preference if profile else None,
        "exercise_habits": profile.exercise_habits if profile else None,
        "smoking": profile.smoking if profile else None,
        "living_style": profile.living_style if profile else None,
        "profile_views": profile.profile_views if profile else 0,
    }