from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import SignUpStatus

if TYPE_CHECKING:
    from app.models.shift import Shift
    from app.models.user import User


class SignUp(TimestampMixin, Base):
    """A volunteer's request for one shift, and the manager's decision on it."""

    __tablename__ = "signups"
    __table_args__ = (
        # One sign-up per volunteer per shift (the API's shiftId + volunteerId).
        UniqueConstraint("shift_id", "volunteer_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shift_id: Mapped[int] = mapped_column(ForeignKey("shifts.id", ondelete="CASCADE"))
    volunteer_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[SignUpStatus] = mapped_column(
        Enum(SignUpStatus, name="status", native_enum=False, create_constraint=True, length=20),
        default=SignUpStatus.REQUESTED,
        server_default=SignUpStatus.REQUESTED.value,
    )
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    shift: Mapped[Shift] = relationship(back_populates="signups")
    volunteer: Mapped[User] = relationship(back_populates="signups", foreign_keys=[volunteer_id])
    decided_by: Mapped[User | None] = relationship(foreign_keys=[decided_by_id])

    def __repr__(self) -> str:
        return (
            f"<SignUp id={self.id} shift_id={self.shift_id} "
            f"volunteer_id={self.volunteer_id} status={self.status}>"
        )
