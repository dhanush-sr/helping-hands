"""HH-15 post a shift: TC-SHIFT-01, TC-SHIFT-02, TC-SHIFT-03, store scope and busy periods."""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import bcrypt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app import security
from app.db.session import get_db, make_engine
from app.main import create_app
from app.models import Base, BusyPeriod, Shift, ShiftStatus, Store, User, UserRole

PASSWORD = "Test@1234"
USERS = {
    "admin": UserRole.ADMIN,
    "meera": UserRole.STORE_MANAGER,
    "rahul": UserRole.STORE_MANAGER,
    "volunteer": UserRole.VOLUNTEER,
}
# Fixed "now" for the tests: 1 Nov 2026, 09:00 IST.
NOW = datetime(2026, 11, 1, 3, 30, tzinfo=UTC)
DIWALI_SAT = date(2026, 11, 7)


def fast_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=4)).decode()


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(security, "utcnow", lambda: NOW)
    engine = make_engine(f"sqlite:///{tmp_path / 'shifts.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with sessions() as db:
        users = {
            name: User(
                email=f"{name}@example.org",
                full_name=name.title(),
                password_hash=fast_hash(PASSWORD),
                role=role,
            )
            for name, role in USERS.items()
        }
        koramangala = Store(name="Koramangala", location="80 Feet Road", manager=users["meera"])
        indiranagar = Store(name="Indiranagar", location="100 Feet Road", manager=users["rahul"])
        closed = Store(
            name="Closed Store", location="Nowhere", manager=users["meera"], is_active=False
        )
        diwali = BusyPeriod(
            name="Diwali weekend", start_date=DIWALI_SAT, end_date=DIWALI_SAT + timedelta(days=1)
        )
        db.add_all([*users.values(), koramangala, indiranagar, closed, diwali])
        db.commit()
        ids = SimpleNamespace(
            koramangala=koramangala.id,
            indiranagar=indiranagar.id,
            closed=closed.id,
            diwali=diwali.id,
            meera=users["meera"].id,
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


def shift_body(store_id: int, **changes) -> dict:
    body = {
        "storeId": store_id,
        "date": DIWALI_SAT.isoformat(),
        "startTime": "10:00",
        "endTime": "14:00",
        "task": "Billing counter",
        "slotsNeeded": 3,
    }
    body.update(changes)
    return body


def post(client, headers, body):
    return client.post("/api/v1/shifts", json=body, headers=headers)


def shift_count(world) -> int:
    with world.sessions() as db:
        return db.scalar(select(func.count()).select_from(Shift))


def test_manager_posts_a_shift(client, world, as_user):  # TC-SHIFT-01
    body = shift_body(world.ids.koramangala, busyPeriodId=world.ids.diwali, notes="Festive rush")
    response = post(client, as_user("meera"), body)

    assert response.status_code == 201
    created = response.json()
    assert created == {"shiftId": created["shiftId"], "status": "OPEN", "freeSlots": 3}

    with world.sessions() as db:
        shift = db.get(Shift, created["shiftId"])
        assert shift.status is ShiftStatus.OPEN
        assert shift.task == "Billing counter"
        assert shift.description == "Festive rush"
        assert shift.busy_period_id == world.ids.diwali
        assert shift.created_by_id == world.ids.meera
        # 10:00 to 14:00 IST is stored as 04:30 to 08:30 UTC.
        assert shift.starts_at.replace(tzinfo=None) == datetime(2026, 11, 7, 4, 30)
        assert shift.ends_at.replace(tzinfo=None) == datetime(2026, 11, 7, 8, 30)


def test_busy_period_and_notes_are_optional(client, world, as_user):
    response = post(client, as_user("meera"), shift_body(world.ids.koramangala))
    assert response.status_code == 201


@pytest.mark.parametrize("end", ["09:00", "10:00"])
def test_end_must_be_after_start(client, world, as_user, end):  # TC-SHIFT-02
    response = post(client, as_user("meera"), shift_body(world.ids.koramangala, endTime=end))

    assert response.status_code == 400
    assert response.json() == {
        "code": "INVALID_SHIFT_TIMES",
        "message": "The end time must be after the start time.",
    }
    assert shift_count(world) == 0


@pytest.mark.parametrize("slots", [0, -2, 101])
def test_volunteers_needed_must_be_1_to_100(client, world, as_user, slots):  # TC-SHIFT-03
    body = shift_body(world.ids.koramangala, slotsNeeded=slots)
    response = post(client, as_user("meera"), body)

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_SLOTS"
    assert shift_count(world) == 0


@pytest.mark.parametrize(
    ("day", "start", "end"),
    [("2026-10-31", "10:00", "14:00"), ("2026-11-01", "08:00", "12:00")],
)
def test_shift_cannot_start_in_the_past(client, world, as_user, day, start, end):
    # Now is 1 Nov, 09:00 IST: yesterday, and earlier this morning, are both refused.
    body = shift_body(world.ids.koramangala, date=day, startTime=start, endTime=end)
    response = post(client, as_user("meera"), body)
    assert response.status_code == 400
    assert response.json()["code"] == "SHIFT_IN_PAST"


def test_later_today_is_fine(client, world, as_user):
    body = shift_body(world.ids.koramangala, date="2026-11-01", startTime="18:00", endTime="21:00")
    assert post(client, as_user("meera"), body).status_code == 201


def test_manager_cannot_post_for_another_store(client, world, as_user):
    response = post(client, as_user("meera"), shift_body(world.ids.indiranagar))
    assert response.status_code == 403
    assert response.json()["code"] == "STORE_FORBIDDEN"
    assert shift_count(world) == 0


@pytest.mark.parametrize("name", ["admin", "volunteer"])
def test_only_store_managers_post_shifts(client, world, as_user, name):
    response = post(client, as_user(name), shift_body(world.ids.koramangala))
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


def test_unknown_store_is_404_and_inactive_store_is_refused(client, world, as_user):
    meera = as_user("meera")
    assert post(client, meera, shift_body(999)).status_code == 404
    inactive = post(client, meera, shift_body(world.ids.closed))
    assert inactive.status_code == 400
    assert inactive.json()["code"] == "STORE_INACTIVE"


def test_busy_period_must_exist(client, world, as_user):
    response = post(client, as_user("meera"), shift_body(world.ids.koramangala, busyPeriodId=999))
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_BUSY_PERIOD"


def test_date_must_be_inside_the_busy_period(client, world, as_user):
    body = shift_body(world.ids.koramangala, busyPeriodId=world.ids.diwali, date="2026-11-10")
    response = post(client, as_user("meera"), body)
    assert response.status_code == 400
    assert response.json()["code"] == "OUTSIDE_BUSY_PERIOD"
    assert "Diwali weekend" in response.json()["message"]


def test_missing_fields_are_a_validation_error(client, world, as_user):
    response = post(client, as_user("meera"), {"storeId": world.ids.koramangala})
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_blank_task_is_refused(client, world, as_user):
    response = post(client, as_user("meera"), shift_body(world.ids.koramangala, task="   "))
    assert response.status_code == 422
