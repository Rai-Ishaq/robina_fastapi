from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.database import engine, Base
from app.routers import (
    auth, profile, matches,
    interests, chat, notifications,
    settings, premium,calls
)
import app.models.user
import app.models.profile
import app.models.interest
import app.models.message
import app.models.notification
import app.models.match
import app.models.otp
import app.models.profile_view
import app.models.premium
import os
import app.models.call_log

Base.metadata.create_all(bind=engine)
os.makedirs("uploads/profiles", exist_ok=True)

app = FastAPI(
    title="Robina Matrimonial API",
    description="Backend API for Robina Matrimonial App",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount(
    "/uploads",
    StaticFiles(directory="uploads"),
    name="uploads"
)

app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(matches.router)
app.include_router(interests.router)
app.include_router(chat.router)
app.include_router(notifications.router)
app.include_router(settings.router)
app.include_router(premium.router)
app.include_router(calls.router)

@app.get("/")
def root():
    return {
        "app": "Robina Matrimonial API",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
def health():
    return {"status": "healthy"}