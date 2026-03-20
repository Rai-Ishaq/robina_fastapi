from pydantic import BaseModel
from typing import Optional

class NotificationResponse(BaseModel):
    id: str
    type: str
    message: str
    is_read: bool
    created_at: str

    class Config:
        from_attributes = True