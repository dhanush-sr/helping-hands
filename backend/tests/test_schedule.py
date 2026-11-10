"""HH-26 My Schedule and withdrawing (HH-F-019, HH-F-016): TC-SCHED-01 and TC-WD-01."""

from datetime import UTC, date, datetime, time, timedelta
from types import SimpleNamespace

import bcrypt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import security
from app.db.session import get_db, make_engine
from app.main import create_app
from app.models import (
    Attendance,
    Base,
    Shift,
    ShiftStatus,
    SignUp,
    SignUpStatus,
    Store,
    User,
    UserRole,
)
from app.services.shifts import store_time

PASSWORD = "Test@1234"
NOW = datetime(2026, 11, 4, 3, 30, tzinfo=UTC)  # Wednesday 4 Nov 2026, 09:00 IST
MON, THU, SAT = date(2026, 11, 2), date(2026, 11, 5), date(2026, 11, 7)


def fast_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=4)).decode()


@pytest.fixture
def world(tmp_path, monkeypatch):
    """Asha has a past shift with attendance, a confirmed one soon, and one too close to drop."""
    monkeypatch.setattr(security, "utcnow", lambda: NOW)
    engine = make_engine(f"sqlite:///{tmp_path / 'schedule.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with sessions() as db:
        meera = User(
            email="meera@example.org",
            full_name="Meera",
            password_hash=fast_hash(PASSWORD),
            role=UserRole.STORE_MANAGER,
        )
        asha = User(
            email="asha@example.org",
            full_name="Asha",
            password_hash=fast_hash(PASSWORD),
            role=UserRole.VOLUNTEER,
        )
        ravi = User(
            email="ravi@example.org",
            full_name="Ravi",
            password_hash=fast_hash(PASSWORD),
            role=UserRole.VOLUNTEER,
        )
        store = Store(name="Koramangala", location="80 Feet Road", manager=meera)

        def shift(task, day, start, end, status=ShiftStatus.OPEN):
            return Shift(
                store=store,
                task=task,
                starts_at=store_time(day, time(start)),
                ends_at=store_time(day, time(end)),
                slots=3,
                status=status,
            )

        done = shift("Monday billing", MON, 10, 13)  # 3 h, already over
        # Starts in 29 hours: past the 24-hour cutoff, so it can still be dropped.
        soon = shift("Saturday packing", SAT, 10, 14)  # 4 h
        # Starts in 5 hours: inside the cutoff, so it cannot.
        locked = Shift(
            store=store,
            task="Tonight restocking",
            starts_at=NOW + timedelta(hours=5),
            ends_at=NOW + timedelta(hours=8),
            slots=3,
        )
        pending = shift("Thursday help desk", THU, 10, 12)  # 2 h, still REQUESTED
        declined = shift("Declined one", THU, 14, 16)

        done_signup = SignUp(shift=done, volunteer=asha, status=SignUpStatus.CONFIRMED)
        signups = [
            done_signup,
            SignUp(shift=soon, volunteer=asha, status=SignUpStatus.CONFIRMED),
            SignUp(shift=locked, volunteer=asha, status=SignUpStatus.CONFIRMED),
            SignUp(shift=pending, volunteer=asha, status=SignUpStatus.REQUESTED),
            SignUp(shift=declined, volunteer=asha, status=SignUpStatus.DECLINED),
            SignUp(shift=soon, volunteer=ravi, status=SignUpStatus.CONFIRMED),
        ]
        db.add_all([meera, asha, ravi, store, done, soon, locked, pending, declined, *signups])
        db.flush()
        db.add(
            Attendance(
                signup_id=done_signup.id,
                status="ATTENDED",
                hours_worked=3.0,
                recorded_by_id=meera.id,
            )
        )
        db.commit()
        ids = SimpleNamespace(
            soon_signup=signups[1].id,
            locked_signup=signups[2].id,
            pending_signup=signups[3].id,
            ravi_signup=signups[5].id,
            soon_shift=soon.id,
        )
    yield SimpleNamespace(sessions=sessions, ids=ids)
    engine.dispose()


@pytest.fixture
def client(world):
    def override_get_db():
        with world.sessions() as db:
            yield db

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


@pytest.fixture
def as_user(client):
    def sign_in(name: str) -> dict[str, str]:
        response = client.post(
            "/api/v1/auth/login", json={"email": f"{name}@example.org", "password": PASSWORD}
        )
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return sign_in


def schedule(client, headers) -> dict:
    response = client.get("/api/v1/me/schedule", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_upcoming_shifts_are_listed_soonest_first(client, as_user):  # TC-SCHED-01
    mine = schedule(client, as_user("asha"))

    assert [e["task"] for e in mine["upcoming"]] == [
        "Tonight restocking",
        "Thursday help desk",
        "Saturday packing",
    ]
    assert [e["status"] for e in mine["upcoming"]] == ["CONFIRMED", "REQUESTED", "CONFIRMED"]
    # A declined sign-up is not something they are waiting on.
    assert "Declined one" not in [e["task"] for e in mine["upcoming"]]


def test_past_shifts_show_the_hours_recorded(client, as_user):  # TC-SCHED-01
    mine = schedule(client, as_user("asha"))

    assert len(mine["past"]) == 1
    done = mine["past"][0]
    assert done["task"] == "Monday billing"
    assert done["attendance"] == "ATTENDED"
    assert done["hoursWorked"] == 3.0
    assert done["date"] == "2026-11-02"
    assert (done["startTime"], done["endTime"]) == ("10:00", "13:00")


def test_hours_this_week_are_counted_against_the_limit(client, as_user):
    mine = schedule(client, as_user("asha"))

    # This week (Mon 2 to Sun 8): 3 done + 4 Saturday + 3 tonight + 2 Thursday = 12.
    assert mine["hoursThisWeek"] == 12.0
    assert mine["weeklyHourLimit"] == 8


def test_a_volunteer_only_sees_their_own_schedule(client, world, as_user):
    mine = schedule(client, as_user("ravi"))

    assert [e["task"] for e in mine["upcoming"]] == ["Saturday packing"]
    assert mine["past"] == []


def test_the_schedule_needs_a_volunteer(client, as_user):
    assert client.get("/api/v1/me/schedule").status_code == 401
    assert client.get("/api/v1/me/schedule", headers=as_user("meera")).status_code == 403


def test_withdraw_is_offered_only_outside_the_cutoff(client, world, as_user):
    mine = schedule(client, as_user("asha"))
    offered = {e["task"]: e["canWithdraw"] for e in mine["upcoming"]}

    assert offered["Saturday packing"] is True  # 29 hours away
    assert offered["Tonight restocking"] is False  # 5 hours away, inside the 24-hour cutoff
    assert offered["Thursday help desk"] is True  # still only requested, but far enough off


def test_withdrawing_frees_the_slot_and_tells_the_manager(client, world, as_user):  # TC-WD-01
    asha, meera = as_user("asha"), as_user("meera")

    gone = client.post(f"/api/v1/signups/{world.ids.soon_signup}/withdraw", headers=asha)

    assert gone.status_code == 200
    assert gone.json()["status"] == "WITHDRAWN"
    # It drops off the schedule and stops counting towards the week.
    mine = schedule(client, asha)
    assert "Saturday packing" not in [e["task"] for e in mine["upcoming"]]
    assert mine["hoursThisWeek"] == 8.0
    bell = client.get("/api/v1/notifications", headers=meera).json()
    assert "withdrew from Saturday packing" in bell["notices"][0]["message"]


def test_withdrawing_inside_the_cutoff_is_refused(client, world, as_user):  # TC-WD-01
    refused = client.post(
        f"/api/v1/signups/{world.ids.locked_signup}/withdraw", headers=as_user("asha")
    )

    assert refused.status_code == 409
    assert refused.json()["code"] == "WITHDRAWAL_CUTOFF"
    with world.sessions() as db:
        assert db.get(SignUp, world.ids.locked_signup).status is SignUpStatus.CONFIRMED


def test_a_volunteer_cannot_withdraw_someone_elses_sign_up(client, world, as_user):
    refused = client.post(
        f"/api/v1/signups/{world.ids.ravi_signup}/withdraw", headers=as_user("asha")
    )

    assert refused.status_code == 403
    with world.sessions() as db:
        assert db.get(SignUp, world.ids.ravi_signup).status is SignUpStatus.CONFIRMED


def test_a_pending_request_can_be_withdrawn_too(client, world, as_user):
    gone = client.post(
        f"/api/v1/signups/{world.ids.pending_signup}/withdraw", headers=as_user("asha")
    )

    assert gone.status_code == 200
    assert gone.json()["status"] == "WITHDRAWN"
