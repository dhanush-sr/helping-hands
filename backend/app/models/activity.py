"""Durable attendance, notifications and audit records for shift and user changes."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Attendance(TimestampMixin, Base):
    __tablename__ = "attendance"
    __table_args__ = (CheckConstraint("hours_worked >= 0", name="hours_nonnegative"),)

    signup_id: Mapped[int] = mapped_column(ForeignKey("signups.id"), primary_key=True)
    status: Mapped[str] = mapped_column(String(12))
    hours_worked: Mapped[float] = mapped_column(Float)
    recorded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))


class Notification(Base):
    """One in-app notice for one person (HH-27). In-app only: no email or SMS."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # Empty for a notice that is not about a shift, such as a role or rule change.
    shift_id: Mapped[int | None] = mapped_column(ForeignKey("shifts.id"))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # NULL means unread; the bell counts these.
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(40))
    target_id: Mapped[int] = mapped_column()
    detail: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
