"""HH-16 browse and filter open shifts: TC-BROWSE-01, free slots, what is hidden, bad filters."""

from datetime import UTC, date, datetime
from types import SimpleNamespace

import bcrypt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import security
from app.db.session import get_db, make_engine
from app.main import create_app
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
from app.services.shifts import store_time

PASSWORD = "Test@1234"
NOW = datetime(2026, 11, 1, 3, 30, tzinfo=UTC)  # 1 Nov 2026, 09:00 IST
SAT, SUN, NEXT_SAT = date(2026, 11, 7), date(2026, 11, 8), date(2026, 11, 14)


def fast_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=4)).decode()


def at(day: date, hour: int) -> datetime:
    return store_time(day, datetime.min.time().replace(hour=hour))


@pytest.fixture
def world(tmp_path, monkeypatch):
    """Shifts at two stores across two busy periods, plus ones that must stay hidden."""
    monkeypatch.setattr(security, "utcnow", lambda: NOW)
    engine = make_engine(f"sqlite:///{tmp_path / 'browse.db'}")
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
            for name, role in [
                ("admin", UserRole.ADMIN),
                ("meera", UserRole.STORE_MANAGER),
                ("asha", UserRole.VOLUNTEER),
                ("ravi", UserRole.VOLUNTEER),
            ]
        }
        kor = Store(name="Koramangala", location="80 Feet Road", manager=users["meera"])
        ind = Store(name="Indiranagar", location="100 Feet Road")
        closed = Store(name="Closed Store", location="Nowhere", is_active=False)
        diwali = BusyPeriod(name="Diwali weekend", start_date=SAT, end_date=SUN)
        rush = BusyPeriod(name="Weekend rush", start_date=NEXT_SAT, end_date=NEXT_SAT)

        def shift(store, day, start, end, task, slots=3, period=None, status=ShiftStatus.OPEN):
            return Shift(
                store=store,
                busy_period=period,
                task=task,
                starts_at=at(day, start),
                ends_at=at(day, end),
                slots=slots,
                status=status,
            )

        billing = shift(kor, SAT, 10, 14, "Billing counter", period=diwali)
        restock = shift(ind, SAT, 14, 18, "Restocking shelves", period=diwali)
        desk = shift(kor, SUN, 10, 14, "Customer help desk", period=diwali)
        packing = shift(ind, NEXT_SAT, 11, 15, "Packing and bagging", period=rush)
        hidden = [
            shift(kor, SAT, 16, 19, "Queue management", slots=1, status=ShiftStatus.FILLED),
            shift(kor, SUN, 15, 18, "Cancelled one", status=ShiftStatus.CANCELLED),
            shift(closed, SAT, 10, 14, "At a closed store"),
            Shift(  # already started (now is 09:00 on 1 Nov)
                store=kor,
                task="Started already",
                starts_at=at(date(2026, 11, 1), 8),
                ends_at=at(date(2026, 11, 1), 12),
                slots=2,
            ),
        ]
        signups = [
            SignUp(shift=billing, volunteer=users["asha"], status=SignUpStatus.CONFIRMED),
            SignUp(shift=billing, volunteer=users["ravi"], status=SignUpStatus.REQUESTED),
        ]
        db.add_all([*users.values(), billing, restock, desk, packing, *hidden, *signups])
        db.commit()
        ids = SimpleNamespace(
            kor=kor.id,
            ind=ind.id,
            diwali=diwali.id,
            rush=rush.id,
            billing=billing.id,
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


def browse(client, headers, **filters):
    response = client.get("/api/v1/shifts", params=filters, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def tasks(shifts) -> list[str]:
    return [shift["task"] for shift in shifts]


def test_no_filters_lists_upcoming_open_shifts_earliest_first(client, as_user):
    shifts = browse(client, as_user("asha"))
    # Filled, cancelled, started and closed-store shifts are left out.
    assert tasks(shifts) == [
        "Billing counter",
        "Restocking shelves",
        "Customer help desk",
        "Packing and bagging",
    ]


def test_each_shift_shows_store_date_time_task_and_free_slots(client, world, as_user):
    billing = browse(client, as_user("asha"))[0]
    assert billing == {
        "shiftId": world.ids.billing,
        "store": "Koramangala",
        "storeId": world.ids.kor,
        "busyPeriod": "Diwali weekend",
        "busyPeriodId": world.ids.diwali,
        "date": "2026-11-07",
        "startTime": "10:00",  # store time (IST), not UTC
        "endTime": "14:00",
        "task": "Billing counter",
        "slotsNeeded": 3,
        "freeSlots": 2,  # one confirmed; the pending request doesn't take a slot
        "status": "OPEN",
    }


def test_filters_combine(client, world, as_user):  # TC-BROWSE-01
    asha = as_user("asha")
    assert tasks(browse(client, asha, storeId=world.ids.kor)) == [
        "Billing counter",
        "Customer help desk",
    ]
    assert tasks(browse(client, asha, busyPeriodId=world.ids.rush)) == ["Packing and bagging"]
    assert tasks(browse(client, asha, date="2026-11-07")) == [
        "Billing counter",
        "Restocking shelves",
    ]
    assert tasks(browse(client, asha, task="BILL")) == ["Billing counter"]  # part, any case
    combined = browse(
        client, asha, storeId=world.ids.ind, busyPeriodId=world.ids.diwali, date="2026-11-07"
    )
    assert tasks(combined) == ["Restocking shelves"]
    assert browse(client, asha, storeId=world.ids.ind, task="desk") == []


def test_status_filter_shows_other_statuses(client, as_user):
    assert tasks(browse(client, as_user("meera"), status="FILLED")) == ["Queue management"]


def test_every_role_can_browse(client, as_user):
    for name in ("admin", "meera", "asha"):
        assert len(browse(client, as_user(name))) == 4


def test_browsing_needs_sign_in(client):
    assert client.get("/api/v1/shifts").status_code == 401


@pytest.mark.parametrize(
    "params",
    [{"status": "OPENISH"}, {"storeId": "abc"}, {"busyPeriodId": "-1"}, {"date": "07/11/2026"}],
)
def test_bad_filters_are_400(client, as_user, params):
    response = client.get("/api/v1/shifts", params=params, headers=as_user("asha"))
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_FILTER"
