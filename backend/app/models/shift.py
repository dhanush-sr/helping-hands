from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import ShiftStatus

if TYPE_CHECKING:
    from app.models.busy_period import BusyPeriod
    from app.models.signup import SignUp
    from app.models.store import Store
    from app.models.user import User


class Shift(TimestampMixin, Base):
    """A block of time at one store where a number of volunteers (slots) are needed."""

    __tablename__ = "shifts"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ends_after_starts"),
        CheckConstraint("slots >= 1", name="slots_at_least_one"),
        # Browsing open shifts (HH-16) filters on status and orders by start time.
        Index("ix_shifts_status_starts_at", "status", "starts_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="CASCADE"), index=True)
    busy_period_id: Mapped[int | None] = mapped_column(
        ForeignKey("busy_periods.id", ondelete="SET NULL"), index=True
    )
    task: Mapped[str] = mapped_column(String(120))  # e.g. "Restocking shelves"
    description: Mapped[str | None] = mapped_column(Text)
    # The shift's date is the date part of starts_at.
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    slots: Mapped[int] = mapped_column(Integer)
    status: Mapped[ShiftStatus] = mapped_column(
        Enum(ShiftStatus, name="status", native_enum=False, create_constraint=True, length=20),
        default=ShiftStatus.OPEN,
        server_default=ShiftStatus.OPEN.value,
    )
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    store: Mapped[Store] = relationship(back_populates="shifts")
    busy_period: Mapped[BusyPeriod | None] = relationship(back_populates="shifts")
    created_by: Mapped[User | None] = relationship()
    signups: Mapped[list[SignUp]] = relationship(
        back_populates="shift", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"<Shift id={self.id} store_id={self.store_id} status={self.status}>"
