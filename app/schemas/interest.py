from pydantic import BaseModel
from typing import Optional
from uuid import UUID

class SendInterestRequest(BaseModel):
    receiver_id: str

class InterestActionRequest(BaseModel):
    interest_id: str
    action: str  # accept / decline

class InterestResponse(BaseModel):
    id: str
    sender_id: str
    receiver_id: str
    status: str
    sender_name: Optional[str]
    sender_city: Optional[str]
    sender_photo: Optional[str]
    sender_age: Optional[int]
    created_at: str

    class Config:
        from_attributes = True