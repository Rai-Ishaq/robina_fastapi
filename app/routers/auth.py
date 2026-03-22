from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.database import get_db
from app.models.user import User
from app.models.profile import Profile
from app.models.otp import OTP
from app.schemas.auth import (
    SignupRequest, LoginRequest, OTPVerifyRequest,
    ResendOTPRequest, ForgotPasswordRequest,
    ResetPasswordRequest, ChangePasswordRequest,
    TokenResponse, MessageResponse, GoogleSignInRequest
)
from app.core.security import (
    hash_password, verify_password, create_access_token
)
from app.core.email import generate_otp, send_otp_email
from app.utils.helpers import get_current_user
import firebase_admin
from firebase_admin import auth as firebase_auth, credentials
import os
import json

# ── Firebase Admin Init ───────────────────────────────────────
if not firebase_admin._apps:
    firebase_creds = os.getenv("FIREBASE_CREDENTIALS")
    if firebase_creds:
        cred = credentials.Certificate(json.loads(firebase_creds))
    else:
        cred = credentials.Certificate("firebase_service_account.json")
    firebase_admin.initialize_app(cred)

router = APIRouter(prefix="/auth", tags=["Authentication"])

# ── SIGNUP ────────────────────────────────────────────────────
@router.post("/signup", response_model=MessageResponse)
def signup(request: SignupRequest, db: Session = Depends(get_db)):
    # Check email exists
    if db.query(User).filter(User.email == request.email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Check phone exists
    if db.query(User).filter(User.phone == request.phone).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone number already registered"
        )

    # Create user
    user = User(
        full_name=request.full_name,
        email=request.email,
        phone=request.phone,
        country_code=request.country_code,
        password_hash=hash_password(request.password),
        gender=request.gender,
        is_verified=False
    )
    db.add(user)
    db.flush()

    # Create empty profile
    profile = Profile(user_id=user.id, setup_step=0)
    db.add(profile)

    # Generate and save OTP
    otp_code = generate_otp()
    otp = OTP(
        email=request.email,
        code=otp_code,
        expires_at=datetime.utcnow() + timedelta(minutes=10)
    )
    db.add(otp)
    db.commit()

    # Send OTP email
    email_sent = send_otp_email(request.email, otp_code, "verification")
    if not email_sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send OTP email"
        )

    return MessageResponse(
        message="Account created. OTP sent to your email.",
        success=True
    )

# ── VERIFY OTP ────────────────────────────────────────────────
@router.post("/verify-otp", response_model=MessageResponse)
def verify_otp(request: OTPVerifyRequest, db: Session = Depends(get_db)):
    otp = db.query(OTP).filter(
        OTP.email == request.email,
        OTP.code == request.otp,
        OTP.is_used == False,
        OTP.expires_at > datetime.utcnow()
    ).order_by(OTP.created_at.desc()).first()

    if not otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP"
        )

    otp.is_used = True

    if request.flow == "signup":
        user = db.query(User).filter(User.email == request.email).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        user.is_verified = True

    db.commit()

    return MessageResponse(
        message="OTP verified successfully",
        success=True
    )

# ── RESEND OTP ────────────────────────────────────────────────
@router.post("/resend-otp", response_model=MessageResponse)
def resend_otp(request: ResendOTPRequest, db: Session = Depends(get_db)):
    db.query(OTP).filter(
        OTP.email == request.email,
        OTP.is_used == False
    ).update({"is_used": True})

    otp_code = generate_otp()
    otp = OTP(
        email=request.email,
        code=otp_code,
        expires_at=datetime.utcnow() + timedelta(minutes=10)
    )
    db.add(otp)
    db.commit()

    purpose = "verification" if request.flow == "signup" else "reset"
    email_sent = send_otp_email(request.email, otp_code, purpose)
    if not email_sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send OTP"
        )

    return MessageResponse(message="OTP resent successfully", success=True)

# ── LOGIN ─────────────────────────────────────────────────────
@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == request.email).first()

    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated"
        )

    user.last_seen = datetime.utcnow()
    db.commit()

    token = create_access_token(
        data={"sub": str(user.id)},
        remember_me=request.remember_me
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=str(user.id),
        is_verified=user.is_verified,
        profile_complete=user.profile_complete,
        full_name=user.full_name
    )

# ── GOOGLE SIGN IN ────────────────────────────────────────────
@router.post("/google-signin", response_model=TokenResponse)
def google_signin(request: GoogleSignInRequest, db: Session = Depends(get_db)):
    # Firebase se token verify karo
    try:
        decoded_token = firebase_auth.verify_id_token(request.id_token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token"
        )

    email = decoded_token.get("email")
    full_name = decoded_token.get("name", "User")
    google_uid = decoded_token.get("uid")

    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email not found in Google token"
        )

    # User pehle se hai ya naya banao
    user = db.query(User).filter(User.email == email).first()

    if not user:
        # Naya user banao
        user = User(
            full_name=full_name,
            email=email,
            phone=None,
            country_code="+92",
            password_hash=hash_password(google_uid),
            gender="male",  # Default — profile setup mein update hoga
            is_verified=True,
            google_uid=google_uid,
        )
        db.add(user)
        db.flush()

        # Empty profile banao
        profile = Profile(user_id=user.id, setup_step=0)
        db.add(profile)
        db.commit()
    else:
        # Existing user — google_uid save karo agar nahi hai
        if not user.google_uid:
            user.google_uid = google_uid
        user.last_seen = datetime.utcnow()
        db.commit()

    token = create_access_token(data={"sub": str(user.id)})

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=str(user.id),
        is_verified=user.is_verified,
        profile_complete=user.profile_complete,
        full_name=user.full_name
    )

# ── FORGOT PASSWORD ───────────────────────────────────────────
@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        return MessageResponse(
            message="If this email exists, OTP has been sent",
            success=True
        )

    db.query(OTP).filter(
        OTP.email == request.email,
        OTP.is_used == False
    ).update({"is_used": True})

    otp_code = generate_otp()
    otp = OTP(
        email=request.email,
        code=otp_code,
        expires_at=datetime.utcnow() + timedelta(minutes=10)
    )
    db.add(otp)
    db.commit()

    send_otp_email(request.email, otp_code, "reset")

    return MessageResponse(
        message="If this email exists, OTP has been sent",
        success=True
    )

# ── RESET PASSWORD ────────────────────────────────────────────
@router.post("/reset-password", response_model=MessageResponse)
def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    otp = db.query(OTP).filter(
        OTP.email == request.email,
        OTP.code == request.otp,
        OTP.is_used == True,
    ).order_by(OTP.created_at.desc()).first()

    if not otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP"
        )

    if otp.expires_at < datetime.utcnow() - timedelta(minutes=10):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP has expired. Please request a new one."
        )

    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    user.password_hash = hash_password(request.new_password)
    db.commit()

    return MessageResponse(
        message="Password reset successfully",
        success=True
    )

# ── CHANGE PASSWORD ───────────────────────────────────────────
@router.post("/change-password", response_model=MessageResponse)
def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not verify_password(request.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )

    current_user.password_hash = hash_password(request.new_password)
    db.commit()

    return MessageResponse(message="Password changed successfully", success=True)

# ── DELETE ACCOUNT ────────────────────────────────────────────
@router.delete("/delete-account", response_model=MessageResponse)
def delete_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    db.delete(current_user)
    db.commit()
    return MessageResponse(message="Account deleted successfully", success=True)

# ── ME ────────────────────────────────────────────────────────
@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": str(current_user.id),
        "full_name": current_user.full_name,
        "email": current_user.email,
        "phone": current_user.phone,
        "gender": current_user.gender,
        "is_verified": current_user.is_verified,
        "is_premium": current_user.is_premium,
        "profile_complete": current_user.profile_complete,
        "last_seen": str(current_user.last_seen)
    }