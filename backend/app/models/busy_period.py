from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.shift import Shift


class BusyPeriod(TimestampMixin, Base):
    """A named date range when stores need extra help, e.g. the Diwali weekend."""

    __tablename__ = "busy_periods"
    __table_args__ = (
        # A one-day period (start == end) is allowed; end before start is not.
        CheckConstraint("end_date >= start_date", name="end_not_before_start"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)

    shifts: Mapped[list[Shift]] = relationship(back_populates="busy_period")

    def __repr__(self) -> str:
        return f"<BusyPeriod id={self.id} name={self.name!r} {self.start_date}..{self.end_date}>"
