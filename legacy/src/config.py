from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    DATABASE_URL: str = "sqlite:///./munimji.db"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_WEBHOOK_URL: Optional[str] = None
    SWITCH_GATEWAY_URL: str = "http://localhost:9000"
    SWITCH_SHARED_SECRET: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    JWT_SECRET_KEY: str = "munimji_development_default_jwt_secret_override_in_env"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    GSP_ENVIRONMENT: str = "sandbox"
    WHATSAPP_VERIFY_TOKEN: str = "munimji_meta_verify_token_2026"
    WHATSAPP_ACCESS_TOKEN: Optional[str] = None
    WHATSAPP_APP_SECRET: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

