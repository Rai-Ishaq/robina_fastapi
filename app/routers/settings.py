from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.models.profile import Profile
from app.models.profile_view import ProfileView
from app.utils.helpers import get_verified_user
from datetime import datetime

router = APIRouter(prefix="/settings", tags=["Settings"])

# ── GET PRIVACY SETTINGS ──────────────────────────────────────
@router.get("/privacy")
def get_privacy_settings(
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    profile = db.query(Profile).filter(
        Profile.user_id == current_user.id
    ).first()

    return {
        "show_online_status": profile.show_online_status
            if profile and profile.show_online_status is not None else True,
    }

# ── UPDATE PRIVACY SETTINGS ───────────────────────────────────
@router.put("/privacy")
def update_privacy_settings(
    request: dict,
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

    if 'show_online_status' in request:
        try:
            profile.show_online_status = bool(request['show_online_status'])
        except Exception:
            pass

    profile.updated_at = datetime.utcnow()
    db.commit()

    return {
        "show_online_status": profile.show_online_status,
    }


# ── PROFILE VIEWS LIST ────────────────────────────────────────
@router.get("/profile-views")
def get_profile_views(
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    from datetime import date, timedelta

    today = date.today()
    week_ago = datetime.utcnow() - timedelta(days=7)

    views = db.query(ProfileView, User).join(
        User, User.id == ProfileView.viewer_id
    ).filter(
        ProfileView.viewed_id == current_user.id
    ).order_by(
        ProfileView.viewed_at.desc()
    ).limit(50).all()

    total_count = db.query(ProfileView).filter(
        ProfileView.viewed_id == current_user.id
    ).count()

    today_count = db.query(ProfileView).filter(
        ProfileView.viewed_id == current_user.id,
        ProfileView.viewed_at >= datetime.combine(
            today, datetime.min.time()
        )
    ).count()

    week_count = db.query(ProfileView).filter(
        ProfileView.viewed_id == current_user.id,
        ProfileView.viewed_at >= week_ago
    ).count()

    viewers = []
    for view, viewer in views:
        viewer_profile = db.query(Profile).filter(
            Profile.user_id == viewer.id
        ).first()

        viewers.append({
            "user_id": str(viewer.id),
            "full_name": viewer.full_name,
            "city": viewer_profile.city if viewer_profile else None,
            "age": None,
            "profile_photo": viewer_profile.profile_photo if viewer_profile else None,
            "viewed_at": str(view.viewed_at),
            "verification_status": viewer.verification_status or "none",
            "is_premium": viewer.is_premium or False,
        })

    return {
        "stats": {
            "total": total_count,
            "today": today_count,
            "this_week": week_count,
        },
        "viewers": viewers
    }