"""HH-24 approve or decline a sign-up: TC-APPR-01, TC-STAT-01 and TC-CONC-01.

TC-CONC-01 is the must-pass case in the Test Plan: two managers approving the last free
slot at the same moment must not overbook the shift.
"""

import threading
from datetime import UTC, date, datetime, time
from types import SimpleNamespace

import bcrypt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app import security
from app.db.session import get_db, make_engine
from app.errors import ApiError
from app.main import create_app
from app.models import (
    AuditEvent,
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
from app.services import signups
from app.services.shifts import store_time

PASSWORD = "Test@1234"
NOW = datetime(2026, 11, 2, 3, 30, tzinfo=UTC)  # Monday 2 Nov 2026, 09:00 IST
SAT = date(2026, 11, 7)


def fast_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=4)).decode()


def build(tmp_path, name: str, slots: int, volunteers: int):
    """A store with one manager, an admin, and `volunteers` pending sign-ups on one shift."""
    engine = make_engine(f"sqlite:///{tmp_path / name}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with sessions() as db:
        meera = User(
            email="meera@example.org",
            full_name="Meera",
            password_hash=fast_hash(PASSWORD),
            role=UserRole.STORE_MANAGER,
        )
        admin = User(
            email="admin@example.org",
            full_name="Admin",
            password_hash=fast_hash(PASSWORD),
            role=UserRole.ADMIN,
        )
        rahul = User(
            email="rahul@example.org",
            full_name="Rahul",
            password_hash=fast_hash(PASSWORD),
            role=UserRole.STORE_MANAGER,
        )
        store = Store(name="Koramangala", location="80 Feet Road", manager=meera)
        other = Store(name="Indiranagar", location="100 Feet Road", manager=rahul)
        shift = Shift(
            store=store,
            task="Billing counter",
            starts_at=store_time(SAT, time(10)),
            ends_at=store_time(SAT, time(14)),
            slots=slots,
        )
        pending = []
        for number in range(1, volunteers + 1):
            volunteer = User(
                email=f"v{number}@example.org",
                full_name=f"Volunteer {number}",
                password_hash=fast_hash(PASSWORD),
                role=UserRole.VOLUNTEER,
            )
            pending.append(SignUp(shift=shift, volunteer=volunteer, status=SignUpStatus.REQUESTED))
        db.add_all([meera, admin, rahul, store, other, shift, *pending])
        db.commit()
        ids = SimpleNamespace(
            shift=shift.id,
            signups=[signup.id for signup in pending],
            meera=meera.id,
            admin=admin.id,
            rahul=rahul.id,
        )
    return engine, sessions, ids


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(security, "utcnow", lambda: NOW)
    engine, sessions, ids = build(tmp_path, "decisions.db", slots=2, volunteers=3)
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


def decide(client, headers, signup_id: int, decision: str = "APPROVE"):
    return client.patch(
        f"/api/v1/signups/{signup_id}", json={"decision": decision}, headers=headers
    )


def shift_status(world) -> ShiftStatus:
    with world.sessions() as db:
        return db.get(Shift, world.ids.shift).status


def test_manager_approves_a_sign_up(client, world, as_user):  # TC-APPR-01
    response = decide(client, as_user("meera"), world.ids.signups[0])

    assert response.status_code == 200
    assert response.json() == {
        "signUpId": world.ids.signups[0],
        "status": "CONFIRMED",
        "shiftStatus": "OPEN",  # one of two slots taken
    }
    with world.sessions() as db:
        signup = db.get(SignUp, world.ids.signups[0])
        assert signup.decided_by_id == world.ids.meera
        assert signup.decided_at is not None


def test_the_shift_fills_when_the_last_slot_is_confirmed(client, world, as_user):  # TC-STAT-01
    meera = as_user("meera")
    assert decide(client, meera, world.ids.signups[0]).json()["shiftStatus"] == "OPEN"

    filled = decide(client, meera, world.ids.signups[1])

    assert filled.json()["shiftStatus"] == "FILLED"
    assert shift_status(world) is ShiftStatus.FILLED
    # A filled shift drops out of the open list volunteers browse.
    open_shifts = client.get("/api/v1/shifts", headers=meera).json()
    assert [s["shiftId"] for s in open_shifts] == []


def test_approving_beyond_the_slots_is_refused(client, world, as_user):  # overbooking
    meera = as_user("meera")
    decide(client, meera, world.ids.signups[0])
    decide(client, meera, world.ids.signups[1])

    third = decide(client, meera, world.ids.signups[2])

    assert third.status_code == 409
    assert third.json()["code"] == "SHIFT_FULL"
    with world.sessions() as db:
        confirmed = db.scalars(
            select(SignUp).where(
                SignUp.shift_id == world.ids.shift, SignUp.status == SignUpStatus.CONFIRMED
            )
        ).all()
        assert len(confirmed) == 2  # never more than the slots


def test_declining_a_pending_sign_up(client, world, as_user):
    declined = decide(client, as_user("meera"), world.ids.signups[0], "DECLINE")

    assert declined.json() == {
        "signUpId": world.ids.signups[0],
        "status": "DECLINED",
        "shiftStatus": "OPEN",  # declining never took a slot, so nothing changes
    }
    assert shift_status(world) is ShiftStatus.OPEN


def test_a_filled_shift_opens_again_when_a_volunteer_withdraws(client, world, as_user):
    # TC-STAT-01: the shift follows the confirmed count in both directions.
    meera = as_user("meera")
    decide(client, meera, world.ids.signups[0])
    decide(client, meera, world.ids.signups[1])
    assert shift_status(world) is ShiftStatus.FILLED

    gone = client.post(f"/api/v1/signups/{world.ids.signups[1]}/withdraw", headers=as_user("v2"))

    assert gone.status_code == 200
    assert gone.json()["status"] == "WITHDRAWN"
    assert shift_status(world) is ShiftStatus.OPEN


def test_the_volunteer_is_notified_and_the_decision_is_audited(client, world, as_user):
    decide(client, as_user("meera"), world.ids.signups[0])

    with world.sessions() as db:
        signup = db.get(SignUp, world.ids.signups[0])
        notice = db.scalar(select(Notification).where(Notification.user_id == signup.volunteer_id))
        event = db.scalar(select(AuditEvent).where(AuditEvent.action == "SIGNUP_CONFIRMED"))

    assert notice is not None and "approved" in notice.message
    assert event is not None and event.actor_id == world.ids.meera
    assert event.target_id == world.ids.signups[0]


def test_a_sign_up_is_only_decided_once(client, world, as_user):
    meera = as_user("meera")
    decide(client, meera, world.ids.signups[0])

    again = decide(client, meera, world.ids.signups[0], "DECLINE")

    assert again.status_code == 409
    assert again.json()["code"] == "ALREADY_DECIDED"


def test_only_that_stores_manager_can_decide(client, world, as_user):
    refused = decide(client, as_user("rahul"), world.ids.signups[0])
    assert refused.status_code == 403
    assert refused.json()["code"] == "STORE_FORBIDDEN"

    with world.sessions() as db:
        assert db.get(SignUp, world.ids.signups[0]).status is SignUpStatus.REQUESTED


def test_volunteers_cannot_decide(client, world, as_user):
    assert decide(client, as_user("v1"), world.ids.signups[0]).status_code == 403


def test_an_unknown_sign_up_is_404(client, as_user):
    assert decide(client, as_user("meera"), 999).status_code == 404


def test_two_managers_approving_the_last_slot(tmp_path, monkeypatch):  # TC-CONC-01
    """The must-pass case: one slot, two approvals at once, exactly one succeeds.

    Both threads are held at a barrier so they are inside ``decide`` together. The shift
    row is locked first, so the second one only gets through after the first has committed,
    and then sees the slot already taken.
    """
    monkeypatch.setattr(security, "utcnow", lambda: NOW)
    engine, sessions, ids = build(tmp_path, "concurrent.db", slots=1, volunteers=2)
    try:
        both_ready = threading.Barrier(2, timeout=10)
        results: list[tuple[str, object]] = []
        lock = threading.Lock()

        def approve(decider_id: int, signup_id: int) -> None:
            with sessions() as db:
                decider = db.get(User, decider_id)
                both_ready.wait()  # neither starts until the other is here too
                try:
                    signup = signups.decide(db, decider, signup_id, approve=True)
                    outcome: tuple[str, object] = ("ok", signup.status)
                except ApiError as refusal:
                    outcome = ("refused", refusal.code)
            with lock:
                results.append(outcome)

        threads = [
            threading.Thread(target=approve, args=(ids.meera, ids.signups[0])),
            threading.Thread(target=approve, args=(ids.admin, ids.signups[1])),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
            assert not thread.is_alive(), "a decision deadlocked"

        assert len(results) == 2
        outcomes = sorted(kind for kind, _ in results)
        assert outcomes == ["ok", "refused"], f"expected exactly one to win, got {results}"
        assert [detail for kind, detail in results if kind == "refused"] == ["SHIFT_FULL"]

        with sessions() as db:
            confirmed = db.scalars(
                select(SignUp).where(
                    SignUp.shift_id == ids.shift, SignUp.status == SignUpStatus.CONFIRMED
                )
            ).all()
            assert len(confirmed) == 1, "the shift was overbooked"
            assert db.get(Shift, ids.shift).status is ShiftStatus.FILLED
    finally:
        engine.dispose()


def test_a_cancelled_shift_cannot_be_decided(client, world, as_user):
    with world.sessions() as db:
        db.get(Shift, world.ids.shift).status = ShiftStatus.CANCELLED
        db.commit()

    refused = decide(client, as_user("meera"), world.ids.signups[0])

    assert refused.status_code == 409
    assert refused.json()["code"] == "SHIFT_CANCELLED"


def test_decisions_do_not_run_past_the_slot_count_under_repeated_approval(client, world, as_user):
    meera = as_user("meera")
    codes = [decide(client, meera, signup_id).status_code for signup_id in world.ids.signups]

    assert codes == [200, 200, 409]
    with world.sessions() as db:
        shift = db.get(Shift, world.ids.shift)
        assert signups.confirmed_count(shift) == shift.slots



def test_manager_sees_who_asked_for_their_shift(client, world, as_user):
    meera = as_user("meera")
    decide(client, meera, world.ids.signups[0])  # one approved, two still pending

    body = client.get(f"/api/v1/shifts/{world.ids.shift}/signups", headers=meera).json()

    assert body["shiftId"] == world.ids.shift
    assert body["slotsNeeded"] == 2
    assert body["freeSlots"] == 1
    assert [s["status"] for s in body["signUps"]] == ["REQUESTED", "REQUESTED", "CONFIRMED"]
    assert {s["volunteer"] for s in body["signUps"]} == {
        "Volunteer 1",
        "Volunteer 2",
        "Volunteer 3",
    }


def test_another_stores_manager_cannot_see_the_sign_ups(client, world, as_user):
    refused = client.get(f"/api/v1/shifts/{world.ids.shift}/signups", headers=as_user("rahul"))
    assert refused.status_code == 403


def test_volunteers_cannot_see_the_sign_up_list(client, world, as_user):
    assert (
        client.get(f"/api/v1/shifts/{world.ids.shift}/signups", headers=as_user("v1")).status_code
        == 403
    )
