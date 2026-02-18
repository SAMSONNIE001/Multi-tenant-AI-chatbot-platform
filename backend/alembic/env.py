import os
import sys
from pathlib import Path
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context

# Ensure Alembic can import from the backend "app/" package
# backend/alembic/env.py -> parents[1] == backend/
sys.path.append(str(Path(__file__).resolve().parents[1]))

# Import models so Base.metadata is populated for autogenerate
import app.db.models  # noqa: F401, E402
from app.db.base import Base  # noqa: E402

config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set metadata for 'autogenerate' support
target_metadata = Base.metadata


def get_database_url() -> str:
    """
    Prefer DATABASE_URL from environment; fallback to alembic.ini sqlalchemy.url.
    This avoids configparser interpolation issues on Windows and is production-safe.
    """
    env_url = os.getenv("DATABASE_URL")
    if env_url:
        return env_url
    return config.get_main_option("sqlalchemy.url")


def run_migrations_offline() -> None:
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Override sqlalchemy.url in config with our resolved DB URL
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = get_database_url()

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
