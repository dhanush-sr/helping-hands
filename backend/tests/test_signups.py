"""HH-17 sign up for a shift (HH-F-011): TC-SIGN-01, one sign-up per shift, who may sign up,
and that the eligibility check (HH-F-012) is called before anything is saved."""

from datetime import UTC, date, datetime
from types import SimpleNamespace

import bcrypt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app import security
from app.db.session import get_db, make_engine
from app.errors import ApiError
from app.main import create_app
from app.models import Base, Shift, ShiftStatus, SignUp, SignUpStatus, Store, User, UserRole
from app.services import eligibility
from app.services.shifts import store_time

PASSWORD = "Test@1234"
NOW = datetime(2026, 11, 2, 3, 30, tzinfo=UTC)  # 2 Nov 2026, 09:00 IST
SAT = date(2026, 11, 7)


def fast_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=4)).decode()


def at(day: date, hour: int) -> datetime:
    return store_time(day, datetime.min.time().replace(hour=hour))


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(security, "utcnow", lambda: NOW)
    engine = make_engine(f"sqlite:///{tmp_path / 'signups.db'}")
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
        closed = Store(name="Closed Store", location="Nowhere", is_active=False)

        def shift(task, start=10, end=14, slots=2, status=ShiftStatus.OPEN, store=kor, day=SAT):
            return Shift(
                store=store,
                task=task,
                starts_at=at(day, start),
                ends_at=at(day, end),
                slots=slots,
                status=status,
            )

        shifts = {
            "billing": shift("Billing counter"),
            "full": shift("Queue management", slots=1),
            "filled": shift("Packing", slots=1, status=ShiftStatus.FILLED),
            "cancelled": shift("Cancelled one", status=ShiftStatus.CANCELLED),
            "closed_store": shift("At a closed store", store=closed),
            "started": shift("Started already", start=8, end=12, day=date(2026, 11, 2)),
            "declined": shift("Restocking shelves", start=15, end=18),
            "withdrawn": shift("Customer help desk", start=18, end=20),
        }
        signups = [
            SignUp(shift=shifts["full"], volunteer=users["ravi"], status=SignUpStatus.CONFIRMED),
            SignUp(shift=shifts["billing"], volunteer=users["ravi"], status=SignUpStatus.REQUESTED),
            SignUp(
                shift=shifts["declined"],
                volunteer=users["asha"],
                status=SignUpStatus.DECLINED,
                decided_by=users["meera"],
                decided_at=NOW,
            ),
            SignUp(
                shift=shifts["withdrawn"],
                volunteer=users["asha"],
                status=SignUpStatus.WITHDRAWN,
                withdrawn_at=NOW,
            ),
        ]
        db.add_all([*users.values(), *shifts.values(), *signups])
        db.commit()
        ids = SimpleNamespace(**{name: s.id for name, s in shifts.items()})
        ids.asha = users["asha"].id
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


def sign_up(client, shift_id, headers):
    return client.post(f"/api/v1/shifts/{shift_id}/signups", headers=headers)


def signups_of(world, shift_id, volunteer_id):
    with world.sessions() as db:
        return list(
            db.scalars(
                select(SignUp).where(
                    SignUp.shift_id == shift_id, SignUp.volunteer_id == volunteer_id
                )
            )
        )


def signup_count(world) -> int:
    with world.sessions() as db:
        return db.scalar(select(func.count()).select_from(SignUp))


# --- signing up ------------------------------------------------------------------------------


def test_tc_sign_01_volunteer_signs_up_for_an_open_shift(client, world, as_user):
    response = sign_up(client, world.ids.billing, as_user("asha"))

    assert response.status_code == 201
    body = response.json()
    assert body == {
        "signUpId": body["signUpId"],
        "shiftId": world.ids.billing,
        "status": "REQUESTED",
    }
    [stored] = signups_of(world, world.ids.billing, world.ids.asha)
    assert stored.id == body["signUpId"]
    assert stored.status == SignUpStatus.REQUESTED
    assert stored.decided_by_id is None


def test_requested_signup_does_not_take_a_slot(client, world, as_user):
    # Only confirmed sign-ups use slots (HH-F-015); the manager decides later (HH-24).
    sign_up(client, world.ids.billing, as_user("asha"))
    listed = client.get("/api/v1/shifts", headers=as_user("asha")).json()
    billing = next(s for s in listed if s["shiftId"] == world.ids.billing)
    assert billing["freeSlots"] == 2
    assert billing["status"] == "OPEN"


def test_same_volunteer_cannot_sign_up_twice(client, world, as_user):
    headers = as_user("asha")
    assert sign_up(client, world.ids.billing, headers).status_code == 201

    again = sign_up(client, world.ids.billing, headers)

    assert again.status_code == 409
    assert again.json() == {
        "code": "ALREADY_SIGNED_UP",
        "message": "You have already signed up for this shift.",
    }
    assert len(signups_of(world, world.ids.billing, world.ids.asha)) == 1


def test_declined_volunteer_cannot_ask_again(client, world, as_user):
    response = sign_up(client, world.ids.declined, as_user("asha"))
    assert response.status_code == 409
    assert response.json()["code"] == "ALREADY_SIGNED_UP"
    [stored] = signups_of(world, world.ids.declined, world.ids.asha)
    assert stored.status == SignUpStatus.DECLINED


def test_volunteer_can_sign_up_again_after_withdrawing(client, world, as_user):
    response = sign_up(client, world.ids.withdrawn, as_user("asha"))

    assert response.status_code == 201
    assert response.json()["status"] == "REQUESTED"
    [stored] = signups_of(world, world.ids.withdrawn, world.ids.asha)  # same row, reused
    assert stored.id == response.json()["signUpId"]
    assert stored.status == SignUpStatus.REQUESTED
    assert stored.withdrawn_at is None


def test_another_volunteers_request_does_not_block(client, world, as_user):
    # ravi has already asked for billing; asha can still ask.
    assert sign_up(client, world.ids.billing, as_user("asha")).status_code == 201


# --- eligibility (HH-F-012) ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("shift", "code"),
    [
        ("full", "SHIFT_FULL"),
        ("filled", "SHIFT_FULL"),
        ("cancelled", "SHIFT_CANCELLED"),
        ("started", "SHIFT_STARTED"),
        ("closed_store", "STORE_INACTIVE"),
    ],
)
def test_ineligible_signup_is_refused_with_its_code(client, world, as_user, shift, code):
    before = signup_count(world)

    response = sign_up(client, getattr(world.ids, shift), as_user("asha"))

    assert response.status_code == 409
    assert response.json()["code"] == code
    assert signup_count(world) == before


def test_signup_returns_the_eligibility_checks_refusal(client, world, as_user, monkeypatch):
    # HH-18's rules (NOTICE, CLASH, WEEKLY_LIMIT) live in eligibility.check; whatever it
    # refuses with is what the volunteer gets, and nothing is saved.
    calls = []

    def refuse(db, volunteer, shift):
        calls.append((volunteer.id, shift.id))
        raise ApiError(409, "CLASH", "You already hold a shift at this time.")

    monkeypatch.setattr(eligibility, "check", refuse)
    before = signup_count(world)

    response = sign_up(client, world.ids.billing, as_user("asha"))

    assert calls == [(world.ids.asha, world.ids.billing)]
    assert response.status_code == 409
    assert response.json() == {
        "code": "CLASH",
        "message": "You already hold a shift at this time.",
    }
    assert signup_count(world) == before


# --- who may sign up -------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["meera", "admin"])
def test_only_volunteers_sign_up(client, world, as_user, name):
    response = sign_up(client, world.ids.billing, as_user(name))
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


def test_signing_up_needs_a_signed_in_user(client, world):
    response = client.post(f"/api/v1/shifts/{world.ids.billing}/signups")
    assert response.status_code == 401


def test_unknown_shift_gives_404(client, as_user):
    response = sign_up(client, 999, as_user("asha"))
    assert response.status_code == 404
    assert response.json()["code"] == "SHIFT_NOT_FOUND"
