from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class PlanResponse(BaseModel):
    id: str
    name: str
    duration_months: int
    price_pkr: int
    price_per_month: int
    savings_percent: int

    class Config:
        from_attributes = True

class SubscribeRequest(BaseModel):
    plan_id: str
    payment_method: str
    transaction_id: Optional[str] = None

class SubscriptionResponse(BaseModel):
    id: str
    plan_name: str
    status: str
    starts_at: str
    expires_at: str
    payment_method: str

    class Config:
        from_attributes = True