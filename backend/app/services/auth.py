"""Sign in, check a session on every request, sign out (HH-11: HH-F-001, HH-SR-002, HH-SR-003).

Rules:
- Wrong email and wrong password give the same 401, so nobody can find out which emails exist.
- 5 wrong passwords in a row lock the account for 15 minutes.
- A session ends after 30 minutes without a request, at its 12-hour limit, or on sign-out.
"""

import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import security
from app.config import get_settings
from app.errors import ApiError
from app.models import AuthSession, User

BEARER = {"WWW-Authenticate": "Bearer"}


def _invalid_credentials() -> ApiError:
    return ApiError(401, "INVALID_CREDENTIALS", "Incorrect email or password.")


def _not_authenticated() -> ApiError:
    return ApiError(401, "NOT_AUTHENTICATED", "Sign in to continue.", BEARER)


def login(db: Session, email: str, password: str) -> tuple[str, User]:
    """Check the password and start a session. Returns the access token and the user."""
    settings = get_settings()
    now = security.utcnow()
    user = db.scalar(select(User).where(User.email == email.strip().lower()))

    if user is None:
        security.verify_password(password, security.dummy_hash())
        raise _invalid_credentials()

    if user.locked_until is not None and security.as_utc(user.locked_until) > now:
        raise ApiError(
            423,
            "ACCOUNT_LOCKED",
            f"Too many wrong passwords. Try again in {settings.lockout_minutes} minutes.",
        )

    if not security.verify_password(password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.max_failed_logins:
            user.failed_login_attempts = 0
            user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
        db.commit()
        raise _invalid_credentials()

    if not user.is_active:
        raise ApiError(403, "ACCOUNT_DISABLED", "This account is deactivated. Ask an admin.")

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    session = AuthSession(
        id=secrets.token_urlsafe(32),
        user=user,
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=settings.session_max_hours),
    )
    db.add(session)
    db.commit()
    return security.create_token(session.id, user.id, session.expires_at), user


def authenticate(db: Session, token: str | None) -> AuthSession:
    """The live session for a bearer token; marks it as used now. Raises 401 otherwise."""
    claims = security.decode_token(token) if token else None
    session = db.get(AuthSession, claims["sid"]) if claims else None
    if session is None or session.revoked_at is not None or str(session.user_id) != claims["sub"]:
        raise _not_authenticated()

    now = security.utcnow()
    idle = timedelta(minutes=get_settings().session_idle_minutes)
    if now - security.as_utc(session.last_seen_at) > idle or now >= security.as_utc(
        session.expires_at
    ):
        session.revoked_at = now
        db.commit()
        raise ApiError(401, "SESSION_EXPIRED", "Your session has expired. Sign in again.", BEARER)

    if not session.user.is_active:
        session.revoked_at = now
        db.commit()
        raise _not_authenticated()

    # ponytail: one write per request to track idle time; fine for this app's traffic.
    session.last_seen_at = now
    db.commit()
    return session


def logout(db: Session, session: AuthSession) -> None:
    session.revoked_at = security.utcnow()
    db.commit()
