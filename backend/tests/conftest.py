import os
from pathlib import Path

import pytest


TEST_DB_PATH = Path(__file__).resolve().parents[1] / "test_smoke.db"

os.environ.setdefault("ENV", "test")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{TEST_DB_PATH.as_posix()}")


@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_db():
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    yield
