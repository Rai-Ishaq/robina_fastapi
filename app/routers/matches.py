from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from app.database import get_db
from app.models.user import User, GenderEnum
from app.models.profile import Profile
from app.models.match import BlockedUser
from app.utils.helpers import get_verified_user
from datetime import date
from typing import Optional

router = APIRouter(prefix="/matches", tags=["Matches"])

def calculate_age(dob: date) -> int:
    today = date.today()
    return today.year - dob.year - (
        (today.month, today.day) < (dob.month, dob.day)
    )

def calculate_match_score(my_profile: Profile, other_profile: Profile) -> int:
    score = 50
    if not my_profile or not other_profile:
        return score

    if my_profile.pref_city and other_profile.city:
        if my_profile.pref_city.lower() == other_profile.city.lower():
            score += 15

    if other_profile.date_of_birth:
        age = calculate_age(other_profile.date_of_birth)
        pref_min = my_profile.pref_age_min or 18
        pref_max = my_profile.pref_age_max or 45
        if pref_min <= age <= pref_max:
            score += 15

    if my_profile.pref_education and other_profile.education:
        if my_profile.pref_education.lower() in other_profile.education.lower():
            score += 10

    if my_profile.pref_marital_status and other_profile.marital_status:
        if my_profile.pref_marital_status.lower() == other_profile.marital_status.lower():
            score += 10

    if my_profile.pref_caste and other_profile.caste:
        if other_profile.caste in my_profile.pref_caste:
            score += 10

    return min(score, 99)

@router.get("/")
def get_matches(
    city: Optional[str] = Query(None),
    min_age: Optional[int] = Query(None),
    max_age: Optional[int] = Query(None),
    caste: Optional[str] = Query(None),
    education: Optional[str] = Query(None),
    marital_status: Optional[str] = Query(None),
    min_height: Optional[int] = Query(None),
    max_height: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    # Opposite gender
    opposite_gender = (
        GenderEnum.female
        if current_user.gender == GenderEnum.male
        else GenderEnum.male
    )

    # Blocked user IDs
    blocked_ids = [
        str(b.blocked_id) for b in db.query(BlockedUser).filter(
            BlockedUser.blocker_id == current_user.id
        ).all()
    ]

    # Base query
    query = db.query(User, Profile).join(
        Profile, Profile.user_id == User.id
    ).filter(
        User.gender == opposite_gender,
        User.is_active == True,
        User.is_verified == True,
        User.id != current_user.id,
        ~User.id.in_(blocked_ids) if blocked_ids else True
    )

    # Filters
    if city:
        query = query.filter(
            Profile.city.ilike(f"%{city}%")
        )
    if caste:
        query = query.filter(
            Profile.caste.ilike(f"%{caste}%")
        )
    if education:
        query = query.filter(
            Profile.education.ilike(f"%{education}%")
        )
    if marital_status:
        query = query.filter(
            Profile.marital_status == marital_status
        )
    if min_height:
        query = query.filter(Profile.height_cm >= min_height)
    if max_height:
        query = query.filter(Profile.height_cm <= max_height)

    # Get my profile for match score
    my_profile = db.query(Profile).filter(
        Profile.user_id == current_user.id
    ).first()

    # Pagination
    total = query.count()
    results = query.offset((page - 1) * limit).limit(limit).all()

    profiles = []
    for user, profile in results:
        age = None
        if profile.date_of_birth:
            age = calculate_age(profile.date_of_birth)

        # Age filter
        if min_age and age and age < min_age:
            continue
        if max_age and age and age > max_age:
            continue

        score = calculate_match_score(my_profile, profile)

        profiles.append({
            "user_id": str(user.id),
            "full_name": user.full_name,
            "gender": user.gender,
            "age": age,
            "city": profile.city,
            "education": profile.education,
            "profession": profile.profession,
            "profile_photo": profile.profile_photo,
            "marital_status": profile.marital_status,
            "caste": profile.caste,
            "match_score": score,
        })

    profiles.sort(key=lambda x: x["match_score"], reverse=True)

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "profiles": profiles
    }

# ── BLOCK USER ────────────────────────────────────────────────
@router.post("/block/{user_id}")
def block_user(
    user_id: str,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    existing = db.query(BlockedUser).filter(
        BlockedUser.blocker_id == current_user.id,
        BlockedUser.blocked_id == user_id
    ).first()

    if existing:
        db.delete(existing)
        db.commit()
        return {"message": "User unblocked", "blocked": False}

    block = BlockedUser(
        blocker_id=current_user.id,
        blocked_id=user_id
    )
    db.add(block)
    db.commit()
    return {"message": "User blocked", "blocked": True}

# ── BLOCKED LIST ──────────────────────────────────────────────
@router.get("/blocked")
def get_blocked_users(
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    blocked = db.query(BlockedUser, User).join(
        User, User.id == BlockedUser.blocked_id
    ).filter(
        BlockedUser.blocker_id == current_user.id
    ).all()

    return [
        {
            "user_id": str(u.id),
            "full_name": u.full_name,
        }
        for _, u in blocked
    ]