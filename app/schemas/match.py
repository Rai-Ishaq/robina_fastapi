from pydantic import BaseModel
from typing import Optional, List

class MatchFilters(BaseModel):
    city: Optional[str] = None
    min_age: Optional[int] = None
    max_age: Optional[int] = None
    caste: Optional[str] = None
    education: Optional[str] = None
    marital_status: Optional[str] = None
    min_height: Optional[int] = None
    max_height: Optional[int] = None
    page: int = 1
    limit: int = 10

class BlockUserRequest(BaseModel):
    user_id: str