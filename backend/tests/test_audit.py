"""HH-33 audit history (HH-F-023, HH-SR-007): TC-AUDIT-01.

That every change is recorded, that the history can be filtered, that only admins see it,
and that nothing in the app can change or remove an event once written.
"""

from datetime import UTC, date, datetime, time, timedelta
from types import SimpleNamespace

import bcrypt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import security
from app.db.session import get_db, make_engine
from app.main import app as real_app
from app.main import create_app
from app.models import AuditEvent, Base, Shift, SignUp, SignUpStatus, Store, User, UserRole
from app.services import audit
from app.services.shifts import store_time
from tests.test_access import api_routes

PASSWORD = "Test@1234"
NOW = datetime(2026, 11, 4, 3, 30, tzinfo=UTC)  # Wednesday 4 Nov 2026, 09:00 IST
SAT = date(2026, 11, 7)


def fast_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=4)).decode()


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(security, "utcnow", lambda: NOW)
    engine = make_engine(f"sqlite:///{tmp_path / 'audit.db'}")
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
                ("admin", UserRole.ADMIN),
                ("meera", UserRole.STORE_MANAGER),
                ("asha", UserRole.VOLUNTEER),
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
        signup = SignUp(shift=shift, volunteer=people["asha"], status=SignUpStatus.REQUESTED)
        db.add_all([*people.values(), store, shift, signup])
        db.commit()
        ids = SimpleNamespace(
            shift=shift.id, signup=signup.id, **{n: p.id for n, p in people.items()}
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


def history(client, headers, **filters) -> dict:
    response = client.get("/api/v1/admin/audit", params=filters, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_a_sign_up_decision_is_recorded(client, world, as_user):  # TC-AUDIT-01
    client.patch(
        f"/api/v1/signups/{world.ids.signup}",
        json={"decision": "APPROVE"},
        headers=as_user("meera"),
    )

    events = history(client, as_user("admin"))["events"]

    assert len(events) == 1
    event = events[0]
    assert event["action"] == "SIGNUP_CONFIRMED"
    assert event["entity_type"] == "SIGNUP"
    assert event["target_id"] == world.ids.signup
    assert event["actor"] == "Meera"
    assert event["actor_id"] == world.ids.meera
    assert event["created_at"] is not None


def test_shift_changes_and_role_changes_are_recorded(client, world, as_user):
    admin, meera = as_user("admin"), as_user("meera")
    client.patch(
        f"/api/v1/shifts/{world.ids.shift}", json={"task": "Gift wrapping"}, headers=meera
    )
    client.post(f"/api/v1/shifts/{world.ids.shift}/cancel", headers=meera)
    client.patch(
        f"/api/v1/admin/users/{world.ids.asha}",
        json={"role": "STORE_MANAGER", "is_active": True},
        headers=admin,
    )

    events = history(client, admin)["events"]

    by_action = {e["action"]: e for e in events}
    assert by_action["SHIFT_EDITED"]["entity_type"] == "SHIFT"
    assert by_action["SHIFT_CANCELLED"]["entity_type"] == "SHIFT"
    assert by_action["USER_ROLE_CHANGED"]["entity_type"] == "USER"
    assert by_action["USER_ROLE_CHANGED"]["detail"] == "VOLUNTEER -> STORE_MANAGER"


def test_newest_first(client, world, as_user):
    meera = as_user("meera")
    client.patch(f"/api/v1/shifts/{world.ids.shift}", json={"task": "First"}, headers=meera)
    client.patch(f"/api/v1/shifts/{world.ids.shift}", json={"task": "Second"}, headers=meera)

    events = history(client, as_user("admin"))["events"]

    assert [e["detail"] for e in events] == [
        "Your shift Second was updated.",
        "Your shift First was updated.",
    ]


def test_filtering_by_who_and_by_action(client, world, as_user):
    admin, meera = as_user("admin"), as_user("meera")
    client.patch(f"/api/v1/shifts/{world.ids.shift}", json={"task": "Edited"}, headers=meera)
    client.patch(
        f"/api/v1/admin/users/{world.ids.asha}",
        json={"role": "STORE_MANAGER", "is_active": True},
        headers=admin,
    )

    assert {e["actor"] for e in history(client, admin, actor_id=world.ids.meera)["events"]} == {
        "Meera"
    }
    only_roles = history(client, admin, action="USER_ROLE_CHANGED")["events"]
    assert [e["action"] for e in only_roles] == ["USER_ROLE_CHANGED"]
    # The filter list offers what has actually been recorded.
    assert set(history(client, admin)["actions"]) == {"SHIFT_EDITED", "USER_ROLE_CHANGED"}


def test_filtering_by_date(client, world, as_user):
    admin, meera = as_user("admin"), as_user("meera")
    client.patch(f"/api/v1/shifts/{world.ids.shift}", json={"task": "Today"}, headers=meera)
    # Backdate one event to last week.
    with world.sessions() as db:
        old = AuditEvent(
            actor_id=world.ids.meera,
            action="SHIFT_EDITED",
            entity_type="SHIFT",
            target_id=world.ids.shift,
            detail="Last week",
            created_at=NOW - timedelta(days=7),
        )
        db.add(old)
        db.commit()

    today = history(client, admin, since="2026-11-04")["events"]
    both = history(client, admin, since="2026-10-01")["events"]
    old_only = history(client, admin, until="2026-11-03")["events"]

    assert [e["detail"] for e in today] == ["Your shift Today was updated."]
    assert len(both) == 2
    assert [e["detail"] for e in old_only] == ["Last week"]


def test_a_backwards_date_range_is_refused(client, as_user):
    response = client.get(
        "/api/v1/admin/audit",
        params={"since": "2026-11-05", "until": "2026-11-04"},
        headers=as_user("admin"),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_DATE_RANGE"


@pytest.mark.parametrize("name", ["meera", "asha"])
def test_only_admins_see_the_history(client, as_user, name):
    assert client.get("/api/v1/admin/audit", headers=as_user(name)).status_code == 403


def test_the_history_needs_signing_in(client):
    assert client.get("/api/v1/admin/audit").status_code == 401


def test_no_endpoint_can_write_to_the_history():
    """HH-SR-007: events are only ever a side effect, never something a request can post."""
    writable = [
        f"{method} {route.path}"
        for route in api_routes(real_app.routes)
        for method in sorted(route.methods)
        if "audit" in route.path and method not in {"GET", "HEAD", "OPTIONS"}
    ]
    assert writable == []


def test_the_entity_type_follows_the_action():
    assert audit.entity_for("SHIFT_CANCELLED") == "SHIFT"
    assert audit.entity_for("SIGNUP_CONFIRMED") == "SIGNUP"
    assert audit.entity_for("ATTENDANCE_RECORDED") == "SIGNUP"  # attendance hangs off a sign-up
    assert audit.entity_for("USER_ROLE_CHANGED") == "USER"
    assert audit.entity_for("SOMETHING_ELSE") == "OTHER"


def test_attendance_is_recorded_against_the_sign_up(client, world, as_user):
    meera = as_user("meera")
    client.patch(
        f"/api/v1/signups/{world.ids.signup}", json={"decision": "APPROVE"}, headers=meera
    )
    # Move the shift into the past so attendance can be taken.
    with world.sessions() as db:
        shift = db.get(Shift, world.ids.shift)
        shift.starts_at = NOW - timedelta(hours=5)
        shift.ends_at = NOW - timedelta(hours=1)
        db.commit()

    client.put(
        f"/api/v1/shifts/{world.ids.shift}/attendance/{world.ids.signup}",
        json={"status": "ATTENDED", "hours_worked": 4},
        headers=meera,
    )

    events = history(client, as_user("admin"))["events"]
    recorded = next(e for e in events if e["action"] == "ATTENDANCE_RECORDED")
    assert recorded["entity_type"] == "SIGNUP"
    assert recorded["target_id"] == world.ids.signup
