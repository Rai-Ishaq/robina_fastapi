from pydantic import BaseModel, EmailStr, validator
from datetime import date
from typing import Optional
from uuid import UUID

class SignupRequest(BaseModel):
    full_name: str
    email: EmailStr
    phone: str
    country_code: str = "+92"
    password: str
    gender: str
    date_of_birth: date

    @validator("full_name")
    def name_not_empty(cls, v):
        if len(v.strip()) < 2:
            raise ValueError("Full name must be at least 2 characters")
        return v.strip()

    @validator("password")
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @validator("gender")
    def gender_valid(cls, v):
        if v.lower() not in ["male", "female"]:
            raise ValueError("Gender must be male or female")
        return v.lower()

    @validator("phone")
    def phone_valid(cls, v):
        digits = ''.join(filter(str.isdigit, v))
        if len(digits) < 10:
            raise ValueError("Enter a valid phone number")
        return v

class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    remember_me: bool = False

class GoogleSignInRequest(BaseModel):
    id_token: str

class OTPVerifyRequest(BaseModel):
    email: EmailStr
    otp: str
    flow: str = "signup"

    @validator("otp")
    def otp_length(cls, v):
        if len(v) != 6:
            raise ValueError("OTP must be 6 digits")
        return v

class ResendOTPRequest(BaseModel):
    email: EmailStr
    flow: str = "signup"

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str
    new_password: str

    @validator("new_password")
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @validator("new_password")
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    is_verified: bool
    profile_complete: bool
    full_name: str

class MessageResponse(BaseModel):
    message: str
    success: bool = True