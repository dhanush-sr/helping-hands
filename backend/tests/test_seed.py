"""HH-10: the demo data matches the Test Plan and gives every sign-up edge case a shift."""

from datetime import UTC, datetime, timedelta

import bcrypt
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.db.session import make_engine
from app.models import (
    Base,
    BusyPeriod,
    Shift,
    ShiftStatus,
    SignUp,
    SignUpStatus,
    Store,
    User,
    UserRole,
)
from app.seed import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    VOLUNTEER_PASSWORD,
    main,
    reset,
    seed,
    volunteer_email,
)

NOW = datetime(2026, 11, 1, 9, 30, tzinfo=UTC)


def utc(value: datetime) -> datetime:
    """SQLite gives datetimes back without a time zone; they are stored as UTC."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def count(session, model, *where) -> int:
    return session.scalar(select(func.count()).select_from(model).where(*where))


def test_seed_loads_the_test_plan_data(db_session):
    seed(db_session, now=NOW)

    assert count(db_session, User, User.role == UserRole.ADMIN) == 1
    assert count(db_session, User, User.role == UserRole.STORE_MANAGER) == 5
    assert count(db_session, User, User.role == UserRole.VOLUNTEER) == 40
    assert count(db_session, Store) == 5
    assert all(store.manager.role is UserRole.STORE_MANAGER for store in db_session.scalars(
        select(Store)
    ))
    periods = {p.name: (p.start_date.isoformat(), p.end_date.isoformat())
               for p in db_session.scalars(select(BusyPeriod))}
    assert periods == {
        "Diwali weekend": ("2026-11-07", "2026-11-08"),
        "Weekend rush": ("2026-11-14", "2026-11-15"),
    }
    assert count(db_session, Shift) == 26
    assert count(db_session, Shift, Shift.status == ShiftStatus.OPEN) == 25
    assert count(db_session, SignUp, SignUp.status == SignUpStatus.REQUESTED) == 20


def test_edge_case_shifts(db_session):
    ids = seed(db_session, now=NOW)
    shift = {name: db_session.get(Shift, shift_id) for name, shift_id in ids.items()}

    def confirmed(s):
        return [u.volunteer.email for u in s.signups if u.status is SignUpStatus.CONFIRMED]

    # Full: every slot confirmed.
    assert shift["full"].status is ShiftStatus.FILLED
    assert len(confirmed(shift["full"])) == shift["full"].slots

    # Short notice: starts inside the 12-hour window from when the seed ran.
    starts_in = utc(shift["short_notice"].starts_at) - NOW
    assert timedelta(0) < starts_in < timedelta(hours=12)

    # Clash: the two shifts overlap and volunteer01 holds the first one.
    a, b = shift["overlap_a"], shift["overlap_b"]
    assert utc(a.starts_at) < utc(b.ends_at) and utc(b.starts_at) < utc(a.ends_at)
    assert confirmed(a) == [volunteer_email(1)]

    # Back-to-back: the second starts exactly when the first ends; volunteer02 holds the first.
    first, second = shift["back_to_back_a"], shift["back_to_back_b"]
    assert utc(first.ends_at) == utc(second.starts_at)
    assert confirmed(first) == [volunteer_email(2)]
    assert confirmed(second) == []


def test_demo_passwords_are_bcrypt_hashes(db_session):
    seed(db_session, now=NOW)
    admin = db_session.scalar(select(User).where(User.email == ADMIN_EMAIL))
    volunteer = db_session.scalar(select(User).where(User.email == volunteer_email(40)))

    assert bcrypt.checkpw(ADMIN_PASSWORD.encode(), admin.password_hash.encode())
    assert bcrypt.checkpw(VOLUNTEER_PASSWORD.encode(), volunteer.password_hash.encode())
    assert ADMIN_PASSWORD not in admin.password_hash


def test_reset_then_seed_again(db_session):
    seed(db_session, now=NOW)
    reset(db_session)
    assert count(db_session, User) == 0
    seed(db_session, now=NOW)
    assert count(db_session, User) == 46
    assert count(db_session, Shift) == 26


def test_command_runs_on_a_fresh_database_and_does_not_load_twice(tmp_path, capsys):
    engine = make_engine(f"sqlite:///{tmp_path / 'seed.db'}")
    sessions = sessionmaker(bind=engine)

    assert main([], sessions) == 1  # no tables yet
    assert "alembic upgrade head" in capsys.readouterr().out

    Base.metadata.create_all(engine)
    assert main([], sessions) == 0
    assert main([], sessions) == 0  # second run leaves the data alone
    assert "already loaded" in capsys.readouterr().out
    assert main(["--reset"], sessions) == 0

    with sessions() as session:
        assert count(session, User) == 46
    engine.dispose()
