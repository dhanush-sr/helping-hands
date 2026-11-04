"""HH-20: manage accounts and volunteering rules."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import security
from app.api.deps import require_admin
from app.api.v1.auth import UserOut
from app.db.session import get_db
from app.errors import ApiError
from app.models import DEFAULT_SETTINGS, AuditEvent, AuthSession, Setting, User, UserRole
from app.services import rules

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


class UserCreated(BaseModel):
    email: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            to_lower=True,
            max_length=255,
            pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        ),
    ]
    full_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
    ]
    password: str = Field(min_length=8, max_length=72)
    role: UserRole


class UserEdit(BaseModel):
    role: UserRole
    is_active: bool


class AdminUser(UserOut):
    is_active: bool


PositiveHours = Annotated[int, Field(strict=True, gt=0, le=2147483647)]


class Rules(BaseModel):
    weekly_hour_limit: PositiveHours
    min_notice_hours: PositiveHours
    withdrawal_cutoff_hours: PositiveHours


@router.get("/users", response_model=list[AdminUser])
def list_users(db: Session = Depends(get_db)):
    return list(db.scalars(select(User).order_by(User.full_name, User.id)))


@router.post("/users", response_model=AdminUser, status_code=201)
def create_user(body: UserCreated, db: Session = Depends(get_db)):
    if len(body.password.encode()) > 72:
        raise ApiError(400, "INVALID_PASSWORD", "The password must fit within 72 UTF-8 bytes.")
    user = User(
        email=body.email.lower(),
        full_name=body.full_name,
        password_hash=security.hash_password(body.password),
        role=body.role,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "EMAIL_IN_USE", "A user already has this email.") from None
    return user


@router.patch("/users/{user_id}", response_model=AdminUser)
def edit_user(
    user_id: int,
    body: UserEdit,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id, with_for_update=True, populate_existing=True)
    if user is None:
        raise ApiError(404, "USER_NOT_FOUND", "No user with that id.")
    if user.id == actor.id and (body.role != UserRole.ADMIN or not body.is_active):
        raise ApiError(400, "SELF_LOCKOUT", "You cannot remove your own administrator access.")
    if user.role != body.role:
        db.add(
            AuditEvent(
                actor_id=actor.id,
                action="USER_ROLE_CHANGED",
                target_id=user.id,
                detail=f"{user.role.value} -> {body.role.value}",
            )
        )
    if not body.is_active:
        db.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=security.utcnow())
        )
    user.role = body.role
    user.is_active = body.is_active
    db.commit()
    return user


@router.get("/rules", response_model=Rules)
def get_rules(db: Session = Depends(get_db)):
    return {key: rules.value(db, key) for key in DEFAULT_SETTINGS}


@router.put("/rules", response_model=Rules)
def set_rules(body: Rules, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    for key, value in body.model_dump().items():
        setting = db.get(Setting, key, with_for_update=True)
        if setting is None:
            setting = Setting(key=key, description=DEFAULT_SETTINGS[key][1])
            db.add(setting)
        setting.value = value
        setting.updated_by_id = actor.id
    db.commit()
    return body
