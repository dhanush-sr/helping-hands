from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Volunteering rules an admin can change (HH-20). Keys and defaults; the first migration
# inserts these rows so a fresh database always has them.
WEEKLY_HOUR_LIMIT = "weekly_hour_limit"
MIN_NOTICE_HOURS = "min_notice_hours"
WITHDRAWAL_CUTOFF_HOURS = "withdrawal_cutoff_hours"

DEFAULT_SETTINGS: dict[str, tuple[int, str]] = {
    WEEKLY_HOUR_LIMIT: (8, "Most hours a volunteer can hold per week (Monday to Sunday)"),
    MIN_NOTICE_HOURS: (12, "Sign-ups close this many hours before a shift starts"),
    WITHDRAWAL_CUTOFF_HOURS: (24, "Volunteers can withdraw until this many hours before"),
}


class Setting(Base):
    """One named, positive whole-number rule, e.g. weekly_hour_limit = 8."""

    __tablename__ = "settings"
    __table_args__ = (CheckConstraint("value > 0", name="value_positive"),)

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[int] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    def __repr__(self) -> str:
        return f"<Setting {self.key}={self.value}>"
