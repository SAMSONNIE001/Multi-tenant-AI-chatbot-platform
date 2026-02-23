import secrets
from hashlib import sha256
from datetime import datetime, timedelta
from typing import Any, Dict

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ENV = settings.ENV
JWT_SECRET = settings.JWT_SECRET
if not JWT_SECRET and ENV != "dev":
    raise RuntimeError("JWT_SECRET is not set")
if not JWT_SECRET:
    JWT_SECRET = "dev-change-me"
JWT_ALG = "HS256"
JWT_ACCESS_EXP_MINUTES = settings.JWT_ACCESS_EXP_MINUTES
JWT_REFRESH_EXP_DAYS = settings.JWT_REFRESH_EXP_DAYS


def _ensure_bcrypt_limit(password: str) -> None:
    # bcrypt limit is 72 BYTES, not characters
    if len(password.encode("utf-8")) > 72:
        raise ValueError("Password too long (max 72 bytes).")


def hash_password(password: str) -> str:
    _ensure_bcrypt_limit(password)
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    _ensure_bcrypt_limit(password)
    return pwd_context.verify(password, password_hash)


def create_access_token(payload: Dict[str, Any]) -> str:
    to_encode = dict(payload)
    to_encode["typ"] = "access"
    to_encode["exp"] = datetime.utcnow() + timedelta(minutes=JWT_ACCESS_EXP_MINUTES)
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALG)


def create_refresh_token(payload: Dict[str, Any]) -> tuple[str, datetime]:
    expires_at = datetime.utcnow() + timedelta(days=JWT_REFRESH_EXP_DAYS)
    to_encode = dict(payload)
    to_encode["typ"] = "refresh"
    to_encode["jti"] = secrets.token_urlsafe(24)
    to_encode["exp"] = expires_at
    token = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALG)
    return token, expires_at


def decode_token(token: str) -> Dict[str, Any]:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])


def hash_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


__all__ = [
    "JWTError",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "hash_password",
    "hash_token",
    "verify_password",
]
