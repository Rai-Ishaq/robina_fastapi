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
import httpx
from pydantic import BaseModel

router = APIRouter(prefix="/premium", tags=["Premium"])

GOOGLE_PLAY_PACKAGE = "com.robina.robina_matrimonial"

class GooglePlayVerifyRequest(BaseModel):
    product_id: str
    purchase_token: str

async def get_google_access_token() -> str:
    try:
        import google.auth
        import google.auth.transport.requests
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/androidpublisher"]
        )
        request = google.auth.transport.requests.Request()
        credentials.refresh(request)
        return credentials.token
    except Exception:
        return ""

async def verify_google_play_purchase(product_id: str, purchase_token: str):
    try:
        url = (
            f"https://androidpublisher.googleapis.com/androidpublisher/v3/"
            f"applications/{GOOGLE_PLAY_PACKAGE}/purchases/subscriptions/"
            f"{product_id}/tokens/{purchase_token}"
        )
        access_token = await get_google_access_token()
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            if response.status_code == 200:
                return response.json()
            return None
    except Exception:
        return None

def seed_plans(db: Session):
    if db.query(PremiumPlan).count() == 0:
        plans = [
            PremiumPlan(name="1 Month", duration_months=1, price_pkr=999, price_per_month=999, savings_percent=0),
            PremiumPlan(name="6 Months", duration_months=6, price_pkr=4499, price_per_month=749, savings_percent=25),
            PremiumPlan(name="1 Year", duration_months=12, price_pkr=7999, price_per_month=666, savings_percent=33),
        ]
        db.add_all(plans)
        db.commit()

@router.get("/plans")
def get_plans(db: Session = Depends(get_db)):
    seed_plans(db)
    plans = db.query(PremiumPlan).filter(PremiumPlan.is_active == True).all()
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

@router.post("/verify-google-play")
async def verify_google_play(
    request: GooglePlayVerifyRequest,
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    plan_duration = {
        "premium_monthly": 1,
        "premium_6month": 6,
        "premium_yearly": 12,
    }
    duration_months = plan_duration.get(request.product_id)
    if not duration_months:
        raise HTTPException(status_code=400, detail="Invalid product ID")

    db.query(UserSubscription).filter(
        UserSubscription.user_id == current_user.id,
        UserSubscription.status == "active"
    ).update({"status": "cancelled"})

    expires_at = datetime.utcnow() + timedelta(days=duration_months * 30)
    subscription = UserSubscription(
        user_id=current_user.id,
        plan_id=None,
        status="active",
        starts_at=datetime.utcnow(),
        expires_at=expires_at,
        payment_method="google_play",
        transaction_id=request.purchase_token[:100]
    )
    db.add(subscription)
    current_user.is_premium = True
    db.commit()

    return {
        "success": True,
        "message": "Premium activated successfully",
        "expires_at": str(expires_at),
        "is_premium": True,
        "duration_months": duration_months
    }

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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

    db.query(UserSubscription).filter(
        UserSubscription.user_id == current_user.id,
        UserSubscription.status == "active"
    ).update({"status": "cancelled"})

    expires_at = datetime.utcnow() + timedelta(days=plan.duration_months * 30)
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

@router.get("/my-subscription")
def get_my_subscription(
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db)
):
    sub = db.query(UserSubscription, PremiumPlan).outerjoin(
        PremiumPlan, PremiumPlan.id == UserSubscription.plan_id
    ).filter(
        UserSubscription.user_id == current_user.id,
        UserSubscription.status == "active"
    ).first()

    if not sub:
        return {"is_premium": False, "subscription": None}

    subscription, plan = sub

    if subscription.expires_at < datetime.utcnow():
        subscription.status = "expired"
        current_user.is_premium = False
        db.commit()
        return {"is_premium": False, "subscription": None}

    return {
        "is_premium": True,
        "subscription": {
            "id": str(subscription.id),
            "plan_name": plan.name if plan else "Google Play",
            "status": subscription.status,
            "starts_at": str(subscription.starts_at),
            "expires_at": str(subscription.expires_at),
            "payment_method": subscription.payment_method,
            "days_remaining": (subscription.expires_at - datetime.utcnow()).days
        }
    }

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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active subscription found")

    sub.status = "cancelled"
    current_user.is_premium = False
    db.commit()
    return {"message": "Subscription cancelled successfully"}