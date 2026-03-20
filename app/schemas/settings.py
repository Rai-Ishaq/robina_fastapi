from pydantic import BaseModel
from typing import Optional

class PrivacySettingsRequest(BaseModel):
    who_can_see: Optional[str] = None
    who_can_message: Optional[str] = None
    show_online_status: Optional[bool] = None
    read_receipts: Optional[bool] = None

class PrivacySettingsResponse(BaseModel):
    who_can_see: str
    who_can_message: str
    show_online_status: bool
    read_receipts: bool