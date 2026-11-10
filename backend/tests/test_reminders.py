"""HH-28 the 24-hour shift reminder (HH-F-018): TC-NOTE-02.

Driven with a fixed clock, so "24 hours before" is exact rather than roughly now.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app import security
from app.db.session import make_engine
from app.models import (
    Base,
    Notification,
    Shift,
    ShiftStatus,
    SignUp,
    SignUpStatus,
    Store,
    User,
    UserRole,
)
from app.services import reminders

NOW = datetime(2026, 11, 6, 3, 30, tzinfo=UTC)  # Friday 6 Nov 2026, 09:00 IST


@pytest.fixture
def clock(monkeypatch):
    """A clock the test moves by hand."""
    state = {"now": NOW}
    monkeypatch.setattr(security, "utcnow", lambda: state["now"])
    return state


@pytest.fixture
def world(tmp_path, clock):
    """One confirmed sign-up on a shift that starts in 20 hours, plus ones to be skipped."""
    engine = make_engine(f"sqlite:///{tmp_path / 'reminders.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with sessions() as db:
        meera = User(
            email="meera@example.org",
            full_name="Meera",
            password_hash="x",
            role=UserRole.STORE_MANAGER,
        )
        asha = User(
            email="asha@example.org", full_name="Asha", password_hash="x", role=UserRole.VOLUNTEER
        )
        ravi = User(
            email="ravi@example.org", full_name="Ravi", password_hash="x", role=UserRole.VOLUNTEER
        )
        nita = User(
            email="nita@example.org", full_name="Nita", password_hash="x", role=UserRole.VOLUNTEER
        )
        store = Store(name="Koramangala", location="80 Feet Road", manager=meera)

        def shift(task, hours_away, status=ShiftStatus.OPEN):
            start = NOW + timedelta(hours=hours_away)
            return Shift(
                store=store,
                task=task,
                starts_at=start,
                ends_at=start + timedelta(hours=3),
                slots=3,
                status=status,
            )

        tomorrow = shift("Billing counter", 20)  # inside the 24-hour window
        far_off = shift("Next week", 72)  # too far away yet
        cancelled = shift("Called off", 10, ShiftStatus.CANCELLED)
        started = shift("Already running", -2)

        signups = {
            "due": SignUp(shift=tomorrow, volunteer=asha, status=SignUpStatus.CONFIRMED),
            "pending": SignUp(shift=tomorrow, volunteer=ravi, status=SignUpStatus.REQUESTED),
            "far": SignUp(shift=far_off, volunteer=asha, status=SignUpStatus.CONFIRMED),
            "cancelled": SignUp(shift=cancelled, volunteer=asha, status=SignUpStatus.CONFIRMED),
            "started": SignUp(shift=started, volunteer=asha, status=SignUpStatus.CONFIRMED),
            # A different volunteer: one person can only hold one sign-up per shift.
            "withdrawn": SignUp(shift=tomorrow, volunteer=nita, status=SignUpStatus.WITHDRAWN),
        }
        db.add_all([meera, asha, ravi, nita, store, tomorrow, far_off, cancelled, started])
        db.add_all(signups.values())
        db.commit()
        ids = SimpleNamespace(
            asha=asha.id,
            ravi=ravi.id,
            nita=nita.id,
            far_shift=far_off.id,
            **{name: signup.id for name, signup in signups.items()},
        )
    yield SimpleNamespace(sessions=sessions, ids=ids, clock=clock)
    engine.dispose()


def notices_for(world, user_id: int) -> list[str]:
    with world.sessions() as db:
        return list(
            db.scalars(
                select(Notification.message)
                .where(Notification.user_id == user_id)
                .order_by(Notification.id)
            )
        )


def run(world) -> int:
    with world.sessions() as db:
        return reminders.send_due(db)


def test_a_confirmed_volunteer_is_reminded(world):  # TC-NOTE-02
    assert run(world) == 1

    messages = notices_for(world, world.ids.asha)
    assert len(messages) == 1
    assert messages[0] == "Reminder: Billing counter at Koramangala tomorrow, 07 Nov at 05:00."


def test_only_the_due_shift_is_reminded(world):
    run(world)

    with world.sessions() as db:
        reminded = db.scalars(
            select(SignUp.id).where(SignUp.reminded_at.is_not(None))
        ).all()

    assert reminded == [world.ids.due]


def test_pending_withdrawn_cancelled_and_started_are_skipped(world):
    run(world)

    # Ravi's sign-up is only pending and Nita withdrew hers, so neither hears anything.
    assert notices_for(world, world.ids.ravi) == []
    assert notices_for(world, world.ids.nita) == []
    assert len(notices_for(world, world.ids.asha)) == 1  # not the cancelled or started ones


def test_running_again_sends_nothing_more(world):  # the "exactly one reminder" rule
    assert run(world) == 1

    assert run(world) == 0
    assert run(world) == 0
    assert len(notices_for(world, world.ids.asha)) == 1


def test_a_shift_becomes_due_as_the_clock_moves(world):
    assert run(world) == 1  # the 20-hour one
    assert run(world) == 0

    # Two days on, the far-off shift is now within 24 hours.
    world.clock["now"] = NOW + timedelta(days=2)

    assert run(world) == 1
    messages = notices_for(world, world.ids.asha)
    assert len(messages) == 2
    assert "Next week" in messages[1]


def test_a_shift_cancelled_before_the_job_runs_is_not_reminded(world):
    with world.sessions() as db:
        db.get(SignUp, world.ids.far).shift.status = ShiftStatus.CANCELLED
        db.commit()
    world.clock["now"] = NOW + timedelta(days=2)

    assert run(world) == 0
    assert notices_for(world, world.ids.asha) == []


def test_a_volunteer_who_withdraws_first_is_not_reminded(world):
    with world.sessions() as db:
        db.get(SignUp, world.ids.due).status = SignUpStatus.WITHDRAWN
        db.commit()

    assert run(world) == 0
    assert notices_for(world, world.ids.asha) == []


def test_nothing_is_written_when_nothing_is_due(world):
    world.clock["now"] = NOW - timedelta(days=5)  # everything still far off

    assert run(world) == 0
    with world.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Notification)) == 0


def test_the_scheduler_is_off_when_the_setting_says_so(monkeypatch):
    from app import config, scheduler

    monkeypatch.setenv("HH_REMINDERS_ENABLED", "false")
    config.get_settings.cache_clear()
    try:
        assert scheduler.start() is None
    finally:
        config.get_settings.cache_clear()


def test_the_job_survives_a_failure(monkeypatch):
    """A broken run must not stop the schedule (the job swallows and logs)."""
    from app import scheduler

    def explode(*_args, **_kwargs):
        raise RuntimeError("database gone")

    monkeypatch.setattr(scheduler, "SessionLocal", explode)
    scheduler.send_reminders()  # must not raise
