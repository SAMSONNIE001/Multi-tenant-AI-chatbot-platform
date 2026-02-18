import os

class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://app:app@localhost:5432/mtchatbot",
    )

settings = Settings()
