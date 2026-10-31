"""Dependencies shared by the endpoints.

Protect an endpoint by adding ``user: User = Depends(get_current_user)``. Role and store
checks (HH-12) build on ``get_current_user``.
"""

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import AuthSession, User
from app.services import auth

bearer = HTTPBearer(auto_error=False)


def get_current_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> AuthSession:
    return auth.authenticate(db, credentials.credentials if credentials else None)


def get_current_user(session: AuthSession = Depends(get_current_session)) -> User:
    return session.user
