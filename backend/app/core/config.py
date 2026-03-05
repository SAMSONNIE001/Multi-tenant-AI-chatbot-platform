from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ENV: str = "dev"
    JWT_SECRET: str | None = None
    JWT_ACCESS_EXP_MINUTES: int = 15
    JWT_REFRESH_EXP_DAYS: int = 7
    DATABASE_URL: str = "postgresql+psycopg://app:app@localhost:5432/mtchatbot"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800
    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )
    OPENAI_API_KEY: str | None = None
    WIDGET_TOKEN_EXP_MINUTES: int = 30
    HANDOFF_WEBHOOK_URL: str | None = None
    META_GRAPH_API_VERSION: str = "v21.0"
    LOG_LEVEL: str = "INFO"
    GUNICORN_WORKERS: int = 2
    FRONTEND_PUBLIC_BASE_URL: str | None = None
    PASSWORD_RESET_EXP_MINUTES: int = 15
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM: str | None = None
    SMTP_STARTTLS: bool = True
    SMTP_CONNECT_TIMEOUT_SECONDS: int = 15
    EMAIL_PROVIDER: str = "smtp"
    ZEPTOMAIL_API_URL: str = "https://api.zeptomail.com/v1.1/email"
    ZEPTOMAIL_API_KEY: str | None = None
    ZEPTOMAIL_FROM_EMAIL: str | None = None
    ZEPTOMAIL_FROM_NAME: str | None = None

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value):
        if isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()]
        return value

    @field_validator("LOG_LEVEL")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        return (value or "INFO").upper()

    @field_validator("EMAIL_PROVIDER")
    @classmethod
    def _normalize_email_provider(cls, value: str) -> str:
        normalized = (value or "smtp").strip().lower()
        if normalized not in {"smtp", "zeptomail"}:
            raise ValueError("EMAIL_PROVIDER must be one of: smtp, zeptomail")
        return normalized


settings = Settings()
