"""Sign in, sign out and "who am I" (HH-11)."""

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_session, get_current_user
from app.config import get_settings
from app.db.session import get_db
from app.models import AuthSession, User, UserRole
from app.services import auth

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: UserRole


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    idle_timeout_minutes: int
    user: UserOut


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    token, user = auth.login(db, body.email, body.password)
    return LoginResponse(
        access_token=token,
        idle_timeout_minutes=get_settings().session_idle_minutes,
        user=UserOut.model_validate(user),
    )


@router.post("/logout", status_code=204)
def logout(
    session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)
) -> Response:
    auth.logout(db, session)
    return Response(status_code=204)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
