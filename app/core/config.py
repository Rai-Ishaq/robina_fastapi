from pydantic_settings import BaseSettings

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
    BASE_URL: str = "https://robina-fastapi.onrender.com"
    UPLOAD_DIR: str = "uploads"
    AGORA_APP_ID: str
    AGORA_APP_CERTIFICATE: str

    class Config:
        env_file = ".env"

settings = Settings()