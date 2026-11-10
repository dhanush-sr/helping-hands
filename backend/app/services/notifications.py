"""In-app notifications (HH-27: HH-F-017).

Every service that changes a sign-up or a shift calls ``notify`` so the person affected
hears about it the next time they look. Notices are in-app only: nothing is emailed or
texted, which the SRS puts out of scope.

Who hears what:
- the store manager, when a volunteer signs up for or withdraws from their shift
- the volunteer, when their sign-up is approved or declined, or the shift is changed
  or cancelled (HH-22 and HH-24 raise those)

``read_at`` is empty until the person opens their notices, and the bell counts the empty
ones.
"""

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app import security
from app.models import Notification, Shift, User


def notify(db: Session, user_id: int | None, message: str, shift: Shift | None = None) -> None:
    """Queue one notice. Added to the caller's transaction, never committed here.

    ``user_id`` is None when a shift has no manager assigned yet, and nothing is queued.
    """
    if user_id is None:
        return
    db.add(
        Notification(
            user_id=user_id, shift_id=shift.id if shift is not None else None, message=message
        )
    )


def notify_store_manager(db: Session, shift: Shift, message: str) -> None:
    """Tell whoever manages this shift's store. Quiet when the store has no manager."""
    notify(db, shift.store.manager_id, message, shift)


def for_user(db: Session, user: User, limit: int = 50) -> list[Notification]:
    """Newest first. Capped, because the bell shows a short list, not a whole history."""
    return list(
        db.scalars(
            select(Notification)
            .where(Notification.user_id == user.id)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(limit)
        )
    )


def unread_count(db: Session, user: User) -> int:
    return db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
    )


def mark_all_read(db: Session, user: User) -> int:
    """Mark this person's unread notices as read. Returns how many changed."""
    result = db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=security.utcnow())
    )
    db.commit()
    return result.rowcount
