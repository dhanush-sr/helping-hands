from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.signup import SignUp
    from app.models.store import Store


class User(TimestampMixin, Base):
    """Anyone who can sign in: volunteers, store managers and admins."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)  # stored lower-case
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))  # bcrypt hash, never plain text
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="role", native_enum=False, create_constraint=True, length=20)
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())

    # Used by sign-in (HH-11): lock for 15 minutes after 5 failed attempts.
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    managed_stores: Mapped[list[Store]] = relationship(back_populates="manager")
    signups: Mapped[list[SignUp]] = relationship(
        back_populates="volunteer", foreign_keys="SignUp.volunteer_id"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} role={self.role}>"
