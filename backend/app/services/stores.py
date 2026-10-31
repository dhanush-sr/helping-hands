"""Stores and their managers, busy periods (HH-13: HH-F-004, HH-F-005).

Only admins change these (the endpoints use ``require_admin``). Rules:
- Store names are unique. A store has at most one manager, who must be an active
  STORE_MANAGER. Stores are deactivated, never deleted, so past shifts and reports stay.
- A busy period's end date can't be before its start date (a one-day period is fine).
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import BusyPeriod, Store, User, UserRole

KEEP = object()  # "field not sent", as opposed to None meaning "clear it"


def _manager(db: Session, manager_id: int | None) -> User | None:
    if manager_id is None:
        return None
    user = db.get(User, manager_id)
    if user is None or user.role != UserRole.STORE_MANAGER or not user.is_active:
        raise ApiError(400, "INVALID_MANAGER", "Pick an active store manager.")
    return user


def _name_taken() -> ApiError:
    return ApiError(409, "STORE_NAME_TAKEN", "A store with that name already exists.")


def _save(db: Session, store: Store) -> Store:
    try:
        db.commit()
    except IntegrityError as error:  # two admins saving the same name at once
        db.rollback()
        raise _name_taken() from error
    db.refresh(store)
    return store


def list_stores(db: Session, user: User) -> list[Store]:
    """Admins see every store; a store manager sees the active stores they manage."""
    query = select(Store).order_by(Store.name)
    if user.role != UserRole.ADMIN:
        query = query.where(Store.manager_id == user.id, Store.is_active.is_(True))
    return list(db.scalars(query))


def create_store(
    db: Session, name: str, location: str, manager_id: int | None = None
) -> Store:
    if db.scalar(select(Store.id).where(Store.name == name)) is not None:
        raise _name_taken()
    store = Store(name=name, location=location, manager=_manager(db, manager_id))
    db.add(store)
    return _save(db, store)


def update_store(
    db: Session,
    store_id: int,
    *,
    name: str | None = None,
    location: str | None = None,
    manager_id=KEEP,
    is_active: bool | None = None,
) -> Store:
    """Rename, move, assign or clear the manager, or (de)activate a store."""
    store = db.get(Store, store_id)
    if store is None:
        raise ApiError(404, "STORE_NOT_FOUND", "No store with that id.")
    if name is not None and name != store.name:
        if db.scalar(select(Store.id).where(Store.name == name)) is not None:
            raise _name_taken()
        store.name = name
    if location is not None:
        store.location = location
    if manager_id is not KEEP:
        store.manager = _manager(db, manager_id)
    if is_active is not None:
        store.is_active = is_active
    return _save(db, store)


def list_store_managers(db: Session) -> list[User]:
    """Active store managers, for the admin's "assign manager" choice."""
    query = (
        select(User)
        .where(User.role == UserRole.STORE_MANAGER, User.is_active.is_(True))
        .order_by(User.full_name)
    )
    return list(db.scalars(query))


def list_busy_periods(db: Session) -> list[BusyPeriod]:
    return list(db.scalars(select(BusyPeriod).order_by(BusyPeriod.start_date, BusyPeriod.id)))


def create_busy_period(db: Session, name: str, start_date: date, end_date: date) -> BusyPeriod:
    if end_date < start_date:
        raise ApiError(
            400, "INVALID_DATE_RANGE", "The end date can't be before the start date."
        )
    period = BusyPeriod(name=name, start_date=start_date, end_date=end_date)
    db.add(period)
    db.commit()
    db.refresh(period)
    return period
