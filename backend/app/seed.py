"""Demo data for local testing and the sprint demos (HH-10).

Run from ``backend/`` after the migrations:

    alembic upgrade head
    python -m app.seed            # load the demo data into an empty database
    python -m app.seed --reset    # delete users, stores, busy periods, shifts and sign-ups first

It follows the test data in the Test Plan: 5 stores, 5 store managers, 1 admin and 40
volunteers, a normal weekend and the Diwali weekend, open shifts, and one shift for each
sign-up edge case. The weekend dates are fixed; the short-notice shift is placed relative to
the time the script runs, so it is always inside the 12-hour notice window.
"""

import argparse
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta, timezone

import bcrypt
from sqlalchemy import delete, inspect, select
from sqlalchemy.orm import Session

from app.models import (
    BusyPeriod,
    Shift,
    ShiftStatus,
    SignUp,
    SignUpStatus,
    Store,
    User,
    UserRole,
)

IST = timezone(timedelta(hours=5, minutes=30), "IST")
DOMAIN = "helpinghands.example"

ADMIN_EMAIL = f"admin@{DOMAIN}"
ADMIN_PASSWORD = "Admin@123"
MANAGER_PASSWORD = "Manager@123"
VOLUNTEER_PASSWORD = "Volunteer@123"

# (store name, address, manager name)
STORES = [
    ("Koramangala", "80 Feet Road, Koramangala, Bengaluru", "Meera Krishnan"),
    ("Indiranagar", "100 Feet Road, Indiranagar, Bengaluru", "Rahul Menon"),
    ("Jayanagar", "4th Block, Jayanagar, Bengaluru", "Fatima Sheikh"),
    ("Whitefield", "ITPL Main Road, Whitefield, Bengaluru", "Suresh Gowda"),
    ("Malleshwaram", "Sampige Road, Malleshwaram, Bengaluru", "Anita Desai"),
]
FIRST_NAMES = [
    "Aarav", "Ananya", "Arjun", "Diya", "Ishaan", "Kavya", "Rohan", "Sneha", "Vikram", "Priya",
]
LAST_NAMES = ["Sharma", "Iyer", "Reddy", "Nair"]
VOLUNTEER_COUNT = len(FIRST_NAMES) * len(LAST_NAMES)  # 40

DIWALI_SAT, DIWALI_SUN = date(2026, 11, 7), date(2026, 11, 8)
WEEKEND_SAT, WEEKEND_SUN = date(2026, 11, 14), date(2026, 11, 15)

# Shifts every store posts: (day, start hour, end hour, task, slots), times in IST.
REGULAR_SHIFTS = [
    (DIWALI_SAT, 10, 14, "Billing counter", 3),
    (DIWALI_SAT, 14, 18, "Restocking shelves", 2),
    (DIWALI_SUN, 10, 14, "Customer help desk", 2),
    (WEEKEND_SAT, 11, 15, "Packing and bagging", 2),
]


def manager_email(store_name: str) -> str:
    return f"manager.{store_name.lower()}@{DOMAIN}"


def volunteer_email(number: int) -> str:
    return f"volunteer{number:02d}@{DOMAIN}"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def ist(day: date, hour: int) -> datetime:
    """A local store time, stored as UTC so every row uses the same clock."""
    return datetime.combine(day, time(hour), IST).astimezone(UTC)


def has_tables(session: Session) -> bool:
    return inspect(session.get_bind()).has_table("users")


def has_demo_data(session: Session) -> bool:
    return session.scalar(select(User.id).where(User.email == ADMIN_EMAIL)) is not None


def reset(session: Session) -> None:
    """Delete the demo-data tables, children first. The settings rows are kept."""
    for model in (SignUp, Shift, BusyPeriod, Store, User):
        session.execute(delete(model))
    session.commit()


def seed(session: Session, now: datetime | None = None) -> dict[str, int]:
    """Add the demo data and return the ids of the edge-case shifts."""
    now = now or datetime.now(UTC)

    admin = User(
        email=ADMIN_EMAIL,
        full_name="Lakshmi Rao",
        password_hash=hash_password(ADMIN_PASSWORD),
        role=UserRole.ADMIN,
    )

    manager_hash = hash_password(MANAGER_PASSWORD)
    stores = [
        Store(
            name=name,
            location=address,
            manager=User(
                email=manager_email(name),
                full_name=manager,
                password_hash=manager_hash,
                role=UserRole.STORE_MANAGER,
            ),
        )
        for name, address, manager in STORES
    ]
    koramangala, indiranagar, jayanagar, whitefield, malleshwaram = stores

    volunteer_hash = hash_password(VOLUNTEER_PASSWORD)
    names = [f"{first} {last}" for last in LAST_NAMES for first in FIRST_NAMES]
    volunteers = [
        User(
            email=volunteer_email(number),
            full_name=name,
            password_hash=volunteer_hash,
            role=UserRole.VOLUNTEER,
        )
        for number, name in enumerate(names, start=1)
    ]

    diwali = BusyPeriod(name="Diwali weekend", start_date=DIWALI_SAT, end_date=DIWALI_SUN)
    weekend = BusyPeriod(name="Weekend rush", start_date=WEEKEND_SAT, end_date=WEEKEND_SUN)

    def shift(store, day, start, end, task, slots, *, description=None, status=ShiftStatus.OPEN):
        return Shift(
            store=store,
            busy_period=diwali if day in (DIWALI_SAT, DIWALI_SUN) else weekend,
            task=task,
            description=description,
            starts_at=ist(day, start),
            ends_at=ist(day, end),
            slots=slots,
            status=status,
            created_by=store.manager,
        )

    def confirmed(volunteer, shift_):
        return SignUp(
            shift=shift_,
            volunteer=volunteer,
            status=SignUpStatus.CONFIRMED,
            decided_by=shift_.store.manager,
            decided_at=now,
        )

    regular = [shift(store, *plan) for store in stores for plan in REGULAR_SHIFTS]
    # Pending requests for managers to approve or decline (volunteers 11 to 30).
    requests = [
        SignUp(shift=s, volunteer=v, status=SignUpStatus.REQUESTED)
        for s, v in zip(regular, volunteers[10:30], strict=True)
    ]

    # Edge cases for the sign-up rules (TC-SIGN-02 to TC-SIGN-05).
    full = shift(
        koramangala, DIWALI_SAT, 16, 19, "Queue management", 2,
        description="Edge case TC-SIGN-02: both slots are confirmed, so the shift is full.",
        status=ShiftStatus.FILLED,
    )
    start_soon = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=6)
    short_notice = Shift(
        store=indiranagar,
        task="Billing counter",
        description="Edge case TC-SIGN-05: starts within the 12-hour notice window.",
        starts_at=start_soon,
        ends_at=start_soon + timedelta(hours=3),
        slots=2,
        created_by=indiranagar.manager,
    )
    overlap_a = shift(
        jayanagar, DIWALI_SUN, 12, 16, "Restocking shelves", 2,
        description="Edge case TC-SIGN-03: volunteer01 is confirmed here, 12:00 to 16:00.",
    )
    overlap_b = shift(
        whitefield, DIWALI_SUN, 14, 18, "Billing counter", 2,
        description="Edge case TC-SIGN-03: overlaps 14:00 to 16:00 with volunteer01's Jayanagar "
        "shift, so their sign-up must be refused as a clash.",
    )
    back_to_back_a = shift(
        malleshwaram, DIWALI_SUN, 14, 17, "Packing and bagging", 2,
        description="Edge case TC-SIGN-04: volunteer02 is confirmed here, 14:00 to 17:00.",
    )
    back_to_back_b = shift(
        malleshwaram, DIWALI_SUN, 17, 20, "Queue management", 2,
        description="Edge case TC-SIGN-04: starts exactly when volunteer02's shift ends, so "
        "their sign-up must be allowed.",
    )
    edge_signups = [
        confirmed(volunteers[2], full),
        confirmed(volunteers[3], full),
        confirmed(volunteers[0], overlap_a),
        confirmed(volunteers[1], back_to_back_a),
    ]

    session.add_all(
        [admin, *stores, *volunteers, diwali, weekend, *regular, *requests]
        + [full, short_notice, overlap_a, overlap_b, back_to_back_a, back_to_back_b]
        + edge_signups
    )
    session.commit()

    return {
        "full": full.id,
        "short_notice": short_notice.id,
        "overlap_a": overlap_a.id,
        "overlap_b": overlap_b.id,
        "back_to_back_a": back_to_back_a.id,
        "back_to_back_b": back_to_back_b.id,
    }


def main(
    argv: list[str] | None = None, session_factory: Callable[[], Session] | None = None
) -> int:
    parser = argparse.ArgumentParser(description="Load the Helping Hands demo data.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete existing users, stores, busy periods, shifts and sign-ups first",
    )
    args = parser.parse_args(argv)

    if session_factory is None:
        from app.db.session import SessionLocal

        session_factory = SessionLocal

    with session_factory() as session:
        if not has_tables(session):
            print("The database has no tables yet. Run `alembic upgrade head` first.")
            return 1
        if args.reset:
            reset(session)
        elif has_demo_data(session):
            print("Demo data is already loaded. Run `python -m app.seed --reset` to load it again.")
            return 0
        edge = seed(session)

    print("Loaded 5 stores, 5 store managers, 1 admin, 40 volunteers, 2 busy periods, 26 shifts.")
    print(f"Edge-case shift ids: {edge}")
    print(f"Admin:      {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    print(f"Managers:   {manager_email('Koramangala')} (one per store) / {MANAGER_PASSWORD}")
    last_volunteer = volunteer_email(VOLUNTEER_COUNT)
    print(f"Volunteers: {volunteer_email(1)} to {last_volunteer} / {VOLUNTEER_PASSWORD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
