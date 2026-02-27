from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_ENV: str = "development"
    APP_BASE_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:3000"
    CORS_ORIGINS: str = "http://localhost:3000"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://ap_user:ap_pass@localhost:5432/ap_db"
    DATABASE_URL_SYNC: str = "postgresql://ap_user:ap_pass@localhost:5432/ap_db"

    # Redis / Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # MinIO
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET_NAME: str = "ap-documents"
    MINIO_SECURE: bool = False

    # Auth
    JWT_SECRET: str = "dev-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    APPROVAL_TOKEN_SECRET: str = "dev-approval-secret-change-in-production"
    APPROVAL_TOKEN_EXPIRE_HOURS: int = 48

    # AI
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-6"
    USE_CLAUDE_VISION: bool = False

    # OCR
    OCR_MIN_CONFIDENCE: float = 0.75
    DUAL_PASS_MAX_MISMATCHES: int = 1

    # Business Rules
    AUTO_APPROVE_THRESHOLD: float = 5000.00
    DUPLICATE_DETECTION_WINDOW_DAYS: int = 7
    FRAUD_SCORE_MEDIUM_THRESHOLD: int = 20
    FRAUD_SCORE_HIGH_THRESHOLD: int = 40
    FRAUD_SCORE_CRITICAL_THRESHOLD: int = 60

    # Email
    MAIL_ENABLED: bool = False
    MAIL_FROM: str = "ap-system@yourcompany.com"
    MAIL_FROM_NAME: str = "AP Operations"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
