from pydantic import BaseModel
from typing import Optional, List
from datetime import date

class ProfileStep1(BaseModel):
    date_of_birth: Optional[date]
    height_cm: Optional[int]
    weight_kg: Optional[int]
    marital_status: Optional[str]
    caste: Optional[str]
    mother_tongue: Optional[str]

class ProfileStep2(BaseModel):
    house_ownership: Optional[str]
    house_size: Optional[str]
    country: Optional[str]
    city: Optional[str]

class ProfileStep3(BaseModel):
    sect: Optional[str]
    family_status: Optional[str]
    family_values: Optional[str]
    siblings_count: Optional[str]

class ProfileStep4(BaseModel):
    education: Optional[str]
    institution_name: Optional[str]
    profession: Optional[str]
    employment_status: Optional[str]
    annual_income: Optional[str]

class ProfileStep5(BaseModel):
    dietary_preference: Optional[str]
    exercise_habits: Optional[str]
    smoking: Optional[str]
    living_style: Optional[str]

class ProfileStep6(BaseModel):
    pref_age_min: Optional[int] = 18
    pref_age_max: Optional[int] = 35
    pref_caste: Optional[List[str]] = []
    pref_education: Optional[str]
    pref_city: Optional[str]
    pref_marital_status: Optional[str]
    pref_family_status: Optional[str]

class ProfileResponse(BaseModel):
    id: str
    user_id: str
    full_name: str
    gender: str
    city: Optional[str]
    country: Optional[str]
    profile_photo: Optional[str]
    age: Optional[int]
    education: Optional[str]
    profession: Optional[str]
    marital_status: Optional[str]
    caste: Optional[str]
    setup_step: int
    profile_views: int
    match_score: Optional[int] = 0

    class Config:
        from_attributes = True