"""Password hashing, session tokens and the clock used by sign-in (HH-11, HH-SR-002).

Passwords are only ever stored as bcrypt hashes. Tokens are signed JWTs that name a
server-side session, so signing out and the idle timeout can end them before they expire.
"""

import secrets
from datetime import UTC, datetime
from functools import cache

import bcrypt
import jwt

from app.config import get_settings

ALGORITHM = "HS256"


def utcnow() -> datetime:
    """The current time. Tests replace this to move the clock forward."""
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """SQLite returns datetimes without a time zone; every stored time is UTC."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:  # malformed hash, or a password longer than bcrypt's 72 bytes
        return False


@cache
def dummy_hash() -> str:
    """Checked when the email is unknown, so that takes as long as a wrong password."""
    return hash_password(secrets.token_urlsafe(16))


def create_token(session_id: str, user_id: int, expires_at: datetime) -> str:
    claims = {"sub": str(user_id), "sid": session_id, "exp": expires_at}
    return jwt.encode(claims, get_settings().secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    """The token's claims, or None when it is malformed, tampered with or expired."""
    try:
        return jwt.decode(
            token,
            get_settings().secret_key,
            algorithms=[ALGORITHM],
            options={"require": ["sub", "sid", "exp"]},
        )
    except jwt.InvalidTokenError:
        return None
