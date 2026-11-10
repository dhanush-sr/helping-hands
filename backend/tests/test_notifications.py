"""HH-27 in-app notifications (HH-F-017): TC-NOTE-01.

This module answers in snake_case, like the rest of ``activity.py``; the SAD-shaped
endpoints elsewhere use camelCase.

Who hears what, the unread count the bell shows, and that opening them clears it.
"""

from datetime import UTC, date, datetime, time
from types import SimpleNamespace

import bcrypt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import security
from app.db.session import get_db, make_engine
from app.main import create_app
from app.models import Base, Shift, SignUp, SignUpStatus, Store, User, UserRole
from app.services.shifts import store_time

PASSWORD = "Test@1234"
NOW = datetime(2026, 11, 2, 3, 30, tzinfo=UTC)  # Monday 2 Nov 2026, 09:00 IST
SAT = date(2026, 11, 7)


def fast_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=4)).decode()


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(security, "utcnow", lambda: NOW)
    engine = make_engine(f"sqlite:///{tmp_path / 'notices.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with sessions() as db:
        people = {
            name: User(
                email=f"{name}@example.org",
                full_name=name.title(),
                password_hash=fast_hash(PASSWORD),
                role=role,
            )
            for name, role in [
                ("meera", UserRole.STORE_MANAGER),
                ("asha", UserRole.VOLUNTEER),
                ("ravi", UserRole.VOLUNTEER),
            ]
        }
        store = Store(name="Koramangala", location="80 Feet Road", manager=people["meera"])
        shift = Shift(
            store=store,
            task="Billing counter",
            starts_at=store_time(SAT, time(10)),
            ends_at=store_time(SAT, time(14)),
            slots=2,
        )
        db.add_all([*people.values(), store, shift])
        db.commit()
        ids = SimpleNamespace(shift=shift.id, **{n: p.id for n, p in people.items()})
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


def notices(client, headers) -> dict:
    response = client.get("/api/v1/notifications", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def sign_up(client, headers, shift_id: int):
    return client.post(f"/api/v1/shifts/{shift_id}/signups", headers=headers)


def test_the_manager_hears_about_a_new_sign_up(client, world, as_user):  # TC-NOTE-01
    sign_up(client, as_user("asha"), world.ids.shift)

    bell = notices(client, as_user("meera"))

    assert bell["unread"] == 1
    assert bell["notices"][0]["message"] == "Asha asked to help with Billing counter."
    assert bell["notices"][0]["shift_id"] == world.ids.shift
    assert bell["notices"][0]["read_at"] is None


def test_the_volunteer_hears_the_decision(client, world, as_user):
    asha, meera = as_user("asha"), as_user("meera")
    created = sign_up(client, asha, world.ids.shift).json()

    client.patch(
        f"/api/v1/signups/{created['signUpId']}", json={"decision": "APPROVE"}, headers=meera
    )

    bell = notices(client, asha)
    assert bell["unread"] == 1
    assert "approved" in bell["notices"][0]["message"]


def test_a_decline_is_also_sent(client, world, as_user):
    asha, meera = as_user("asha"), as_user("meera")
    created = sign_up(client, asha, world.ids.shift).json()

    client.patch(
        f"/api/v1/signups/{created['signUpId']}", json={"decision": "DECLINE"}, headers=meera
    )

    assert "declined" in notices(client, asha)["notices"][0]["message"]


def test_the_manager_hears_about_a_withdrawal(client, world, as_user):
    asha, meera = as_user("asha"), as_user("meera")
    created = sign_up(client, asha, world.ids.shift).json()
    client.post("/api/v1/notifications/read", headers=meera)  # clear the sign-up notice

    client.post(f"/api/v1/signups/{created['signUpId']}/withdraw", headers=asha)

    bell = notices(client, meera)
    assert bell["unread"] == 1
    assert bell["notices"][0]["message"] == "Asha withdrew from Billing counter."


def test_notices_only_reach_the_person_they_are_about(client, world, as_user):
    sign_up(client, as_user("asha"), world.ids.shift)

    # Ravi did nothing, so his bell stays empty even though Asha's sign-up happened.
    assert notices(client, as_user("ravi")) == {"unread": 0, "notices": []}


def test_opening_the_bell_clears_the_count(client, world, as_user):
    asha, meera = as_user("asha"), as_user("meera")
    sign_up(client, asha, world.ids.shift)
    assert notices(client, meera)["unread"] == 1

    opened = client.post("/api/v1/notifications/read", headers=meera)

    assert opened.status_code == 200
    assert opened.json()["unread"] == 0
    assert opened.json()["notices"][0]["read_at"] is not None
    # Still listed after reading: the bell clears, the history stays.
    assert notices(client, meera) == {"unread": 0, "notices": opened.json()["notices"]}


def test_a_later_notice_is_unread_again(client, world, as_user):
    asha, meera = as_user("asha"), as_user("meera")
    created = sign_up(client, asha, world.ids.shift).json()
    client.post("/api/v1/notifications/read", headers=meera)

    client.post(f"/api/v1/signups/{created['signUpId']}/withdraw", headers=asha)

    bell = notices(client, meera)
    assert bell["unread"] == 1
    assert len(bell["notices"]) == 2  # the read one is still there


def test_newest_notice_comes_first(client, world, as_user):
    asha, meera = as_user("asha"), as_user("meera")
    created = sign_up(client, asha, world.ids.shift).json()
    client.post(f"/api/v1/signups/{created['signUpId']}/withdraw", headers=asha)

    messages = [n["message"] for n in notices(client, meera)["notices"]]

    assert messages == [
        "Asha withdrew from Billing counter.",
        "Asha asked to help with Billing counter.",
    ]


def test_the_bell_needs_a_signed_in_user(client):
    assert client.get("/api/v1/notifications").status_code == 401
    assert client.post("/api/v1/notifications/read").status_code == 401


def test_marking_read_touches_nobody_else(client, world, as_user):
    asha, meera = as_user("asha"), as_user("meera")
    created = sign_up(client, asha, world.ids.shift).json()
    client.patch(
        f"/api/v1/signups/{created['signUpId']}", json={"decision": "APPROVE"}, headers=meera
    )

    client.post("/api/v1/notifications/read", headers=meera)

    assert notices(client, asha)["unread"] == 1  # Asha's approval notice is still unread


def test_a_store_without_a_manager_does_not_break_sign_up(client, world, as_user):
    with world.sessions() as db:
        db.get(Shift, world.ids.shift).store.manager_id = None
        db.commit()

    created = sign_up(client, as_user("asha"), world.ids.shift)

    assert created.status_code == 201
    with world.sessions() as db:
        assert db.get(SignUp, created.json()["signUpId"]).status is SignUpStatus.REQUESTED
