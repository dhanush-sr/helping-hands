from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.shift import Shift
    from app.models.user import User


class Store(TimestampMixin, Base):
    """A store that asks for volunteer help. Has at most one store manager (set by an admin)."""

    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    location: Mapped[str] = mapped_column(String(255))
    # One manager per store. Nullable so a store can be created before its manager exists;
    # the API (HH-13) checks the user has the STORE_MANAGER role.
    manager_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    # Stores are deactivated, not deleted, so past shifts and reports stay intact.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())

    manager: Mapped[User | None] = relationship(back_populates="managed_stores")
    shifts: Mapped[list[Shift]] = relationship(back_populates="store")

    def __repr__(self) -> str:
        return f"<Store id={self.id} name={self.name!r}>"
