"""HH-18 sign-up rules (HH-F-012, HH-F-013): TC-SIGN-02 to TC-SIGN-06.

The rules are checked by one service function, ``eligibility.check``, so most of these call
it directly; the last few go through the API to show the code reaches the volunteer and that
nothing is saved when a sign-up is refused.

The week in these tests: Monday 2 Nov 2026 (when "now" is) to Sunday 8 Nov. Monday 9 Nov
starts the next week.
"""

from datetime import UTC, date, datetime, time
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
from app.models import (
    DEFAULT_SETTINGS,
    MIN_NOTICE_HOURS,
    WEEKLY_HOUR_LIMIT,
    Base,
    Setting,
    Shift,
    ShiftStatus,
    SignUp,
    SignUpStatus,
    Store,
    User,
    UserRole,
)
from app.services import eligibility
from app.services.shifts import store_time

PASSWORD = "Test@1234"
NOW = datetime(2026, 11, 2, 3, 30, tzinfo=UTC)  # Monday 2 Nov 2026, 09:00 IST
MON, SAT, SUN, NEXT_MON = (
    date(2026, 11, 2),
    date(2026, 11, 7),
    date(2026, 11, 8),
    date(2026, 11, 9),
)


def fast_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=4)).decode()


def at(day: date, hour: int) -> datetime:
    return store_time(day, time(hour))


@pytest.fixture
def world(tmp_path, monkeypatch):
    """Asha is confirmed on a 4-hour Saturday shift; Ravi holds nothing.

    The other shifts are each set up to trip exactly one rule, so a test can name it.
    """
    monkeypatch.setattr(security, "utcnow", lambda: NOW)
    engine = make_engine(f"sqlite:///{tmp_path / 'eligibility.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with sessions() as db:
        for key, (value, description) in DEFAULT_SETTINGS.items():
            db.add(Setting(key=key, value=value, description=description))
        users = {
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
        store = Store(name="Koramangala", location="80 Feet Road", manager=users["meera"])

        def shift(task, day, start, end, slots=2, status=ShiftStatus.OPEN):
            return Shift(
                store=store,
                task=task,
                starts_at=at(day, start),
                ends_at=at(day, end),
                slots=slots,
                status=status,
            )

        shifts = {
            # Asha holds this one: Saturday 10:00 to 14:00, 4 hours.
            "held": shift("Billing counter", SAT, 10, 14),
            "overlap": shift("Restocking", SAT, 13, 17),  # shares 13:00 to 14:00
            "back_to_back": shift("Gift wrapping", SAT, 14, 17),  # starts as the held one ends
            "sunday_exact": shift("Help desk", SUN, 10, 14),  # 4 h: takes Asha to exactly 8
            "sunday_over": shift("Packing", SUN, 10, 15),  # 5 h: takes Asha to 9
            "next_week": shift("Packing", NEXT_MON, 10, 15),  # same 5 h, but a new week
            "soon": shift("Evening rush", MON, 18, 21),  # starts in 9 h: inside the notice
            "exactly_notice": shift("Night shelf fill", MON, 21, 23),  # starts in exactly 12 h
            "full": shift("Queue management", SAT, 18, 20, slots=1),
            "cancelled": shift("Called off", SAT, 10, 14, status=ShiftStatus.CANCELLED),
        }
        signups = [
            SignUp(
                shift=shifts["held"], volunteer=users["asha"], status=SignUpStatus.CONFIRMED
            ),
            # Ravi fills the one-slot shift, so it has no room for anyone else.
            SignUp(shift=shifts["full"], volunteer=users["ravi"], status=SignUpStatus.CONFIRMED),
            # Withdrawn and declined sign-ups must not count as "held".
            SignUp(
                shift=shifts["cancelled"],
                volunteer=users["ravi"],
                status=SignUpStatus.REQUESTED,
            ),
            SignUp(
                shift=shifts["overlap"], volunteer=users["ravi"], status=SignUpStatus.WITHDRAWN
            ),
            SignUp(
                shift=shifts["sunday_over"],
                volunteer=users["ravi"],
                status=SignUpStatus.DECLINED,
            ),
        ]
        db.add_all([*users.values(), store, *shifts.values(), *signups])
        db.commit()
        ids = SimpleNamespace(
            users={name: user.id for name, user in users.items()},
            shifts={name: shift.id for name, shift in shifts.items()},
        )
    yield SimpleNamespace(sessions=sessions, users=ids.users, shifts=ids.shifts)
    engine.dispose()


def outcome(world, volunteer: str, shift: str) -> str | None:
    """The refusal code from ``eligibility.check``, or None when the sign-up is allowed."""
    with world.sessions() as db:
        try:
            eligibility.check(
                db, db.get(User, world.users[volunteer]), db.get(Shift, world.shifts[shift])
            )
        except ApiError as refusal:
            return refusal.code
        return None


def set_rule(world, key: str, value: int) -> None:
    with world.sessions() as db:
        db.get(Setting, key).value = value
        db.commit()


# --- the shift's own state -------------------------------------------------------------------


def test_full_shift_is_refused(world):  # TC-SIGN-02
    assert outcome(world, "asha", "full") == "SHIFT_FULL"


def test_cancelled_shift_is_refused(world):
    assert outcome(world, "asha", "cancelled") == "SHIFT_CANCELLED"


# --- minimum notice --------------------------------------------------------------------------


def test_shift_inside_the_notice_window_is_refused(world):  # TC-SIGN-05
    # Now is Monday 09:00; this shift starts at 18:00, 9 hours away, inside the 12-hour notice.
    assert outcome(world, "ravi", "soon") == "NOTICE"


def test_exactly_the_minimum_notice_is_allowed(world):
    # Starts at 21:00, exactly 12 hours away: the rule refuses less than the notice, not equal.
    assert outcome(world, "ravi", "exactly_notice") is None


def test_notice_follows_the_admin_setting(world):
    assert outcome(world, "ravi", "soon") == "NOTICE"
    set_rule(world, MIN_NOTICE_HOURS, 4)  # an admin relaxes it (HH-20)
    assert outcome(world, "ravi", "soon") is None


# --- clashes ---------------------------------------------------------------------------------


def test_overlapping_shift_is_refused(world):  # TC-SIGN-03
    # Asha holds Saturday 10:00 to 14:00; this one runs 13:00 to 17:00.
    assert outcome(world, "asha", "overlap") == "CLASH"


def test_the_clash_message_names_the_other_shift(world):
    with world.sessions() as db:
        with pytest.raises(ApiError) as raised:
            eligibility.check(
                db, db.get(User, world.users["asha"]), db.get(Shift, world.shifts["overlap"])
            )
    assert "Billing counter" in raised.value.message
    assert "Koramangala" in raised.value.message


def test_back_to_back_shifts_are_allowed(world):  # TC-SIGN-04
    # Starts at 14:00, exactly when Asha's held shift ends. Touching is not overlapping.
    assert outcome(world, "asha", "back_to_back") is None


def test_another_volunteers_shifts_do_not_clash(world):
    # Ravi holds nothing, so Asha's Saturday shift is no reason to refuse him.
    assert outcome(world, "ravi", "overlap") is None


def test_withdrawn_and_declined_sign_ups_do_not_clash(world):
    # Ravi withdrew from "overlap" and was declined for "sunday_over"; neither is held.
    assert outcome(world, "ravi", "back_to_back") is None
    assert outcome(world, "ravi", "sunday_over") is None


def test_a_cancelled_shift_does_not_clash(world):
    # Ravi's request on the cancelled Saturday shift must not block the same hours.
    assert outcome(world, "ravi", "overlap") is None


def test_signing_up_again_after_withdrawing_does_not_clash_with_itself(world):
    assert outcome(world, "ravi", "overlap") is None


# --- weekly hour limit -----------------------------------------------------------------------


def test_going_over_the_weekly_limit_is_refused(world):  # TC-SIGN-06
    # Asha holds 4 hours on Saturday; 5 more on Sunday would be 9, over the 8-hour limit.
    assert outcome(world, "asha", "sunday_over") == "WEEKLY_LIMIT"


def test_exactly_reaching_the_weekly_limit_is_allowed(world):
    # 4 held + 4 more = 8, which is the limit itself.
    assert outcome(world, "asha", "sunday_exact") is None


def test_the_limit_is_counted_monday_to_sunday(world):
    # The same 5-hour shift, moved to Monday 9 Nov, falls in a new week and is allowed.
    assert outcome(world, "asha", "sunday_over") == "WEEKLY_LIMIT"
    assert outcome(world, "asha", "next_week") is None


def test_weekly_limit_follows_the_admin_setting(world):
    assert outcome(world, "asha", "sunday_over") == "WEEKLY_LIMIT"
    set_rule(world, WEEKLY_HOUR_LIMIT, 12)
    assert outcome(world, "asha", "sunday_over") is None


def test_the_weekly_limit_message_says_how_much_is_held(world):
    with world.sessions() as db:
        with pytest.raises(ApiError) as raised:
            eligibility.check(
                db, db.get(User, world.users["asha"]), db.get(Shift, world.shifts["sunday_over"])
            )
    assert "8 hour weekly limit" in raised.value.message
    assert "4 hours" in raised.value.message


def test_requested_hours_count_towards_the_limit(world):
    # Not only confirmed ones: a pending request already holds the time.
    with world.sessions() as db:
        signup = db.scalar(
            select(SignUp).where(
                SignUp.volunteer_id == world.users["asha"],
                SignUp.shift_id == world.shifts["held"],
            )
        )
        signup.status = SignUpStatus.REQUESTED
        db.commit()
    assert outcome(world, "asha", "sunday_over") == "WEEKLY_LIMIT"


# --- which rule wins -------------------------------------------------------------------------


def test_the_shift_is_checked_before_the_volunteer(world):
    # "overlap" would clash for Asha, but a cancelled shift is cancelled for everyone.
    assert outcome(world, "asha", "cancelled") == "SHIFT_CANCELLED"


def test_a_clash_is_reported_before_the_weekly_limit(world):
    # "overlap" breaks both rules; the clash is the more useful thing to say.
    assert outcome(world, "asha", "overlap") == "CLASH"


# --- through the API -------------------------------------------------------------------------


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


def signup_count(world) -> int:
    with world.sessions() as db:
        return db.scalar(select(func.count()).select_from(SignUp))


@pytest.mark.parametrize(
    ("shift", "code"),
    [
        ("overlap", "CLASH"),
        ("sunday_over", "WEEKLY_LIMIT"),
        ("full", "SHIFT_FULL"),
    ],
)
def test_a_refused_sign_up_returns_409_and_saves_nothing(client, world, as_user, shift, code):
    before = signup_count(world)

    response = client.post(
        f"/api/v1/shifts/{world.shifts[shift]}/signups", headers=as_user("asha")
    )

    assert response.status_code == 409
    assert response.json()["code"] == code
    assert response.json()["message"]  # the volunteer is told why, not just given a code
    assert signup_count(world) == before


def test_an_allowed_sign_up_still_goes_through(client, world, as_user):
    before = signup_count(world)

    response = client.post(
        f"/api/v1/shifts/{world.shifts['back_to_back']}/signups", headers=as_user("asha")
    )

    assert response.status_code == 201
    assert response.json()["status"] == "REQUESTED"
    assert signup_count(world) == before + 1
