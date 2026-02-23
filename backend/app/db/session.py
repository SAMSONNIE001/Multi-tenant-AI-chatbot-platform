from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

DATABASE_URL = settings.DATABASE_URL

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine_kwargs = {"connect_args": connect_args, "pool_pre_ping": True}
if not DATABASE_URL.startswith("sqlite"):
    engine_kwargs.update(
        {
            "pool_size": settings.DB_POOL_SIZE,
            "max_overflow": settings.DB_MAX_OVERFLOW,
            "pool_timeout": settings.DB_POOL_TIMEOUT,
            "pool_recycle": settings.DB_POOL_RECYCLE,
        }
    )

engine = create_engine(DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
