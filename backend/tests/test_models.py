from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

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

START = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)


def make_user(email: str, role: UserRole = UserRole.VOLUNTEER) -> User:
    return User(email=email, full_name=email.split("@")[0], password_hash="x", role=role)


@pytest.fixture
def shift(db_session) -> Shift:
    manager = make_user("manager@example.org", UserRole.STORE_MANAGER)
    store = Store(name="Koramangala", location="Bengaluru", manager=manager)
    period = BusyPeriod(
        name="Diwali weekend", start_date=date(2026, 11, 7), end_date=date(2026, 11, 8)
    )
    shift = Shift(
        store=store,
        busy_period=period,
        task="Restocking",
        starts_at=START,
        ends_at=START + timedelta(hours=4),
        slots=3,
        created_by=manager,
    )
    db_session.add(shift)
    db_session.commit()
    return shift


def test_defaults_and_relationships(db_session, shift):
    volunteer = make_user("volunteer@example.org")
    db_session.add(SignUp(shift=shift, volunteer=volunteer))
    db_session.commit()
    db_session.refresh(shift)

    assert shift.status is ShiftStatus.OPEN
    assert shift.store.manager.role is UserRole.STORE_MANAGER
    assert shift.busy_period.name == "Diwali weekend"
    assert shift.signups[0].status is SignUpStatus.REQUESTED
    assert shift.signups[0].volunteer.email == "volunteer@example.org"
    assert volunteer.is_active is True
    assert volunteer.failed_login_attempts == 0
    assert shift.created_at is not None


def test_shift_can_be_marked_completed(db_session, shift):
    shift.status = ShiftStatus.COMPLETED
    db_session.commit()
    db_session.refresh(shift)

    assert shift.status is ShiftStatus.COMPLETED


def test_same_volunteer_cannot_sign_up_twice_for_one_shift(db_session, shift):
    volunteer = make_user("twice@example.org")
    db_session.add_all(
        [SignUp(shift=shift, volunteer=volunteer), SignUp(shift=shift, volunteer=volunteer)]
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_same_volunteer_can_sign_up_for_different_shifts(db_session, shift):
    volunteer = make_user("two-shifts@example.org")
    other = Shift(
        store=shift.store,
        task="Billing",
        starts_at=START + timedelta(hours=5),
        ends_at=START + timedelta(hours=8),
        slots=1,
    )
    db_session.add_all(
        [SignUp(shift=shift, volunteer=volunteer), SignUp(shift=other, volunteer=volunteer)]
    )
    db_session.commit()

    assert len(volunteer.signups) == 2


@pytest.mark.parametrize(
    ("ends_at", "slots"),
    [
        (START, 1),  # ends at the same time it starts
        (START - timedelta(hours=1), 1),  # ends before it starts
        (START + timedelta(hours=2), 0),  # no slots
    ],
)
def test_invalid_shift_is_rejected_by_the_database(db_session, shift, ends_at, slots):
    db_session.add(
        Shift(store=shift.store, task="Packing", starts_at=START, ends_at=ends_at, slots=slots)
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_busy_period_end_before_start_is_rejected(db_session):
    db_session.add(
        BusyPeriod(name="Backwards", start_date=date(2026, 11, 8), end_date=date(2026, 11, 7))
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_one_day_busy_period_is_allowed(db_session):
    db_session.add(
        BusyPeriod(name="Sale day", start_date=date(2026, 11, 7), end_date=date(2026, 11, 7))
    )
    db_session.commit()


def test_user_email_is_unique(db_session):
    db_session.add_all([make_user("same@example.org"), make_user("same@example.org")])

    with pytest.raises(IntegrityError):
        db_session.commit()
