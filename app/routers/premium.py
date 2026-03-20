from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.models.premium import PremiumPlan, UserSubscription
from app.schemas.premium import (
    PlanResponse, SubscribeRequest, SubscriptionResponse
)
from app.utils.helpers import get_verified_user
from datetime import datetime, timedelta

router = APIRouter(prefix="/premium", tags=["Premium"])

# ── SEED DEFAULT PLANS ────────────────────────────────────────
def seed_plans(db: Session):
    if db.query(PremiumPlan).count() == 0:
        plans = [
            PremiumPlan(
                name="1 Month",
                duration_months=1,
                price_pkr=999,
                price_per_month=999,
                savings_percent=0
            ),
            PremiumPlan(
                name="6 Months",
                duration_months=6,
                price_pkr=4499,
                price_per_month=749,
                savings_percent=25
            ),
            PremiumPlan(
                name="1 Year",
                duration_months=12,
                price_pkr=7999,
                price_per_month=666,
                savings_percent=33
            ),
        ]
        db.add_all(plans)
        db.commit()

# ── GET PLANS ─────────────────────────────────────────────────
@router.get("/plans")
def get_plans(
    db: Session = Depends(get_db)
):
    seed_plans(db)
    plans = db.query(PremiumPlan).filter(
        PremiumPlan.is_active == True
    ).all()

    return [
        {
            "id": str(p.id),
            "name": p.name,
            "duration_months": p.duration_months,
            "price_pkr": p.price_pkr,
            "price_per_month": p.price_per_month,
            "savings_percent": p.savings_percent,
        }
        for p in plans
    ]

# ── SUBSCRIBE ─────────────────────────────────────────────────
@router.post("/subscribe")
def subscribe(
    request: SubscribeRequest,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    plan = db.query(PremiumPlan).filter(
        PremiumPlan.id == request.plan_id,
        PremiumPlan.is_active == True
    ).first()

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found"
        )

    # Cancel existing active subscription
    db.query(UserSubscription).filter(
        UserSubscription.user_id == current_user.id,
        UserSubscription.status == "active"
    ).update({"status": "cancelled"})

    expires_at = datetime.utcnow() + timedelta(
        days=plan.duration_months * 30
    )

    subscription = UserSubscription(
        user_id=current_user.id,
        plan_id=plan.id,
        status="active",
        starts_at=datetime.utcnow(),
        expires_at=expires_at,
        payment_method=request.payment_method,
        transaction_id=request.transaction_id
    )
    db.add(subscription)

    current_user.is_premium = True
    db.commit()

    return {
        "message": "Subscription activated successfully",
        "plan": plan.name,
        "expires_at": str(expires_at),
        "is_premium": True
    }

# ── GET MY SUBSCRIPTION ───────────────────────────────────────
@router.get("/my-subscription")
def get_my_subscription(
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    sub = db.query(UserSubscription, PremiumPlan).join(
        PremiumPlan, PremiumPlan.id == UserSubscription.plan_id
    ).filter(
        UserSubscription.user_id == current_user.id,
        UserSubscription.status == "active"
    ).first()

    if not sub:
        return {
            "is_premium": False,
            "subscription": None
        }

    subscription, plan = sub

    # Check if expired
    if subscription.expires_at < datetime.utcnow():
        subscription.status = "expired"
        current_user.is_premium = False
        db.commit()
        return {
            "is_premium": False,
            "subscription": None
        }

    return {
        "is_premium": True,
        "subscription": {
            "id": str(subscription.id),
            "plan_name": plan.name,
            "status": subscription.status,
            "starts_at": str(subscription.starts_at),
            "expires_at": str(subscription.expires_at),
            "payment_method": subscription.payment_method,
            "days_remaining": (
                subscription.expires_at - datetime.utcnow()
            ).days
        }
    }

# ── CANCEL SUBSCRIPTION ───────────────────────────────────────
@router.post("/cancel")
def cancel_subscription(
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    sub = db.query(UserSubscription).filter(
        UserSubscription.user_id == current_user.id,
        UserSubscription.status == "active"
    ).first()

    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active subscription found"
        )

    sub.status = "cancelled"
    current_user.is_premium = False
    db.commit()

    return {"message": "Subscription cancelled successfully"}