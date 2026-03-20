from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REMEMBER_ME_EXPIRE_DAYS: int = 30
    MAIL_USERNAME: str
    MAIL_PASSWORD: str
    MAIL_FROM: str
    MAIL_FROM_NAME: str = "Robina Matrimonial"
    APP_NAME: str = "Robina Matrimonial"
    BASE_URL: str = "http://192.168.10.3:8001"
    UPLOAD_DIR: str = "uploads"
    AGORA_APP_ID: str = "8733b70ed503472b96a6ae8107007523"
    AGORA_APP_CERTIFICATE: str = "d00228b50fb84dcfa1f2900d4ffa4679"

    class Config:
        env_file = ".env"

settings = Settings()