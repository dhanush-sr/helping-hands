"""HH-32 coverage and volunteer reports (HH-F-021, HH-F-022): TC-COV-01 and TC-REP-01."""

import csv
import io
from datetime import UTC, date, datetime, time
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
    BusyPeriod,
    Shift,
    SignUp,
    SignUpStatus,
    Store,
    User,
    UserRole,
)
from app.store_clock import store_time

PASSWORD = "Test@1234"
NOW = datetime(2026, 11, 20, 3, 30, tzinfo=UTC)  # after both busy periods
SAT, SUN, LATER = date(2026, 11, 7), date(2026, 11, 8), date(2026, 11, 14)


def fast_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=4)).decode()


@pytest.fixture
def world(tmp_path, monkeypatch):
    """Two stores. Koramangala ran two Diwali shifts; Indiranagar ran one later shift."""
    monkeypatch.setattr(security, "utcnow", lambda: NOW)
    engine = make_engine(f"sqlite:///{tmp_path / 'reports.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with sessions() as db:
        admin = User(
            email="admin@example.org",
            full_name="Admin",
            password_hash=fast_hash(PASSWORD),
            role=UserRole.ADMIN,
        )
        meera = User(
            email="meera@example.org",
            full_name="Meera",
            password_hash=fast_hash(PASSWORD),
            role=UserRole.STORE_MANAGER,
        )
        rahul = User(
            email="rahul@example.org",
            full_name="Rahul",
            password_hash=fast_hash(PASSWORD),
            role=UserRole.STORE_MANAGER,
        )
        spare = User(
            email="spare@example.org",
            full_name="Spare",
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
        kor = Store(name="Koramangala", location="80 Feet Road", manager=meera)
        ind = Store(name="Indiranagar", location="100 Feet Road", manager=rahul)
        diwali = BusyPeriod(name="Diwali weekend", start_date=SAT, end_date=SUN)

        def shift(store, day, start, end, slots, period=None, task="Billing"):
            return Shift(
                store=store,
                busy_period=period,
                task=task,
                starts_at=store_time(day, time(start)),
                ends_at=store_time(day, time(end)),
                slots=slots,
            )

        full = shift(kor, SAT, 10, 14, 2, diwali, "Billing counter")  # 4 h, 2 confirmed
        gap = shift(kor, SUN, 10, 13, 3, diwali, "Help desk")  # 3 h, 1 confirmed: a gap
        other = shift(ind, LATER, 10, 12, 1, None, "Packing")  # different store and week

        asha_full = SignUp(shift=full, volunteer=asha, status=SignUpStatus.CONFIRMED)
        ravi_full = SignUp(shift=full, volunteer=ravi, status=SignUpStatus.CONFIRMED)
        asha_gap = SignUp(shift=gap, volunteer=asha, status=SignUpStatus.CONFIRMED)
        ravi_gap = SignUp(shift=gap, volunteer=ravi, status=SignUpStatus.REQUESTED)
        asha_other = SignUp(shift=other, volunteer=asha, status=SignUpStatus.CONFIRMED)
        db.add_all(
            [
                admin, meera, rahul, spare, asha, ravi, kor, ind, diwali, full, gap, other,
                asha_full, ravi_full, asha_gap, ravi_gap, asha_other,
            ]
        )
        db.flush()
        db.add_all(
            [
                # Asha worked both Diwali shifts; Ravi turned up to one and missed the other.
                Attendance(signup_id=asha_full.id, status="ATTENDED", hours_worked=4.0,
                           recorded_by_id=meera.id),
                Attendance(signup_id=ravi_full.id, status="NO_SHOW", hours_worked=0.0,
                           recorded_by_id=meera.id),
                Attendance(signup_id=asha_gap.id, status="ATTENDED", hours_worked=3.0,
                           recorded_by_id=meera.id),
                Attendance(signup_id=asha_other.id, status="ATTENDED", hours_worked=2.0,
                           recorded_by_id=rahul.id),
            ]
        )
        db.commit()
        ids = SimpleNamespace(
            kor=kor.id, ind=ind.id, diwali=diwali.id, full=full.id, gap=gap.id, other=other.id
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


def report(client, headers, name, **filters) -> dict:
    response = client.get(f"/api/v1/reports/{name}", params=filters, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_coverage_shows_the_gap_on_each_shift(client, world, as_user):  # TC-COV-01
    rows = report(client, as_user("meera"), "coverage", busyPeriodId=world.ids.diwali)["rows"]

    assert [(r["task"], r["slots_needed"], r["confirmed"], r["open_slots"]) for r in rows] == [
        ("Billing counter", 2, 2, 0),
        ("Help desk", 3, 1, 2),  # the gap a manager needs to spot
    ]
    assert rows[0]["busy_period"] == "Diwali weekend"
    assert (rows[0]["date"], rows[0]["start_time"], rows[0]["end_time"]) == (
        "2026-11-07",
        "10:00",
        "14:00",
    )


def test_hours_per_volunteer(client, world, as_user):  # TC-REP-01
    rows = report(client, as_user("admin"), "hours")["rows"]

    assert [(r["volunteer"], r["shifts"], r["hours"]) for r in rows] == [
        ("Asha", 3, 9.0),  # 4 + 3 + 2 across both stores
        # Ravi's only record is a no-show, so he has no hours.
    ]


def test_no_shows_per_volunteer(client, world, as_user):  # TC-REP-01
    rows = report(client, as_user("admin"), "no-shows")["rows"]

    assert [(r["volunteer"], r["no_shows"], r["attended"]) for r in rows] == [("Ravi", 1, 0)]


def test_a_manager_only_sees_their_own_store(client, world, as_user):
    mine = report(client, as_user("meera"), "coverage")["rows"]
    theirs = report(client, as_user("rahul"), "coverage")["rows"]

    assert {r["store"] for r in mine} == {"Koramangala"}
    assert {r["store"] for r in theirs} == {"Indiranagar"}
    # Hours follow the same scope: Meera sees only what was worked at her store.
    assert report(client, as_user("meera"), "hours")["rows"][0]["hours"] == 7.0


def test_a_manager_asking_for_another_store_is_refused(client, world, as_user):
    response = client.get(
        "/api/v1/reports/coverage",
        params={"storeId": world.ids.ind},
        headers=as_user("meera"),
    )
    assert response.status_code == 403
    assert response.json()["code"] == "STORE_FORBIDDEN"


def test_an_admin_can_pick_one_store(client, world, as_user):
    rows = report(client, as_user("admin"), "coverage", storeId=world.ids.ind)["rows"]
    assert {r["store"] for r in rows} == {"Indiranagar"}


def test_a_manager_without_a_store_gets_an_empty_report(client, as_user):
    assert report(client, as_user("spare"), "coverage")["rows"] == []


def test_filtering_by_date(client, world, as_user):
    admin = as_user("admin")

    diwali_only = report(client, admin, "coverage", since="2026-11-07", until="2026-11-08")
    later_only = report(client, admin, "coverage", since="2026-11-09")

    assert {r["task"] for r in diwali_only["rows"]} == {"Billing counter", "Help desk"}
    assert {r["task"] for r in later_only["rows"]} == {"Packing"}


def test_a_backwards_date_range_is_refused(client, as_user):
    response = client.get(
        "/api/v1/reports/coverage",
        params={"since": "2026-11-08", "until": "2026-11-07"},
        headers=as_user("admin"),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_DATE_RANGE"


def test_an_unknown_busy_period_is_refused(client, as_user):
    response = client.get(
        "/api/v1/reports/coverage", params={"busyPeriodId": 999}, headers=as_user("admin")
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_BUSY_PERIOD"


def test_an_unknown_report_name_is_404(client, as_user):
    response = client.get("/api/v1/reports/guesswork", headers=as_user("admin"))
    assert response.status_code == 404
    assert response.json()["code"] == "UNKNOWN_REPORT"


@pytest.mark.parametrize("name", ["coverage", "hours", "no-shows"])
def test_the_csv_matches_what_the_page_shows(client, world, as_user, name):  # TC-REP-01
    admin = as_user("admin")
    shown = report(client, admin, name)

    download = client.get(f"/api/v1/reports/{name}.csv", headers=admin)

    assert download.status_code == 200
    assert download.headers["content-type"].startswith("text/csv")
    assert f'filename="{name}.csv"' in download.headers["content-disposition"]
    table = list(csv.reader(io.StringIO(download.text)))
    assert table[0] == shown["columns"]
    assert len(table) == len(shown["rows"]) + 1
    for line, row in zip(table[1:], shown["rows"], strict=True):
        # An empty value is an empty cell in the spreadsheet, not the text "None".
        assert line == [
            "" if row[column] is None else str(row[column]) for column in shown["columns"]
        ]


def test_an_empty_csv_still_has_its_header(client, as_user):
    download = client.get("/api/v1/reports/coverage.csv", headers=as_user("spare"))

    table = list(csv.reader(io.StringIO(download.text)))
    assert table == [
        [
            "shift_id", "store", "busy_period", "date", "start_time", "end_time",
            "task", "slots_needed", "confirmed", "open_slots", "status",
        ]
    ]


def test_the_csv_follows_the_same_store_scope(client, world, as_user):
    download = client.get("/api/v1/reports/coverage.csv", headers=as_user("rahul"))

    stores = {line[1] for line in list(csv.reader(io.StringIO(download.text)))[1:]}
    assert stores == {"Indiranagar"}


@pytest.mark.parametrize("path", ["/api/v1/reports/coverage", "/api/v1/reports/coverage.csv"])
def test_volunteers_cannot_read_reports(client, as_user, path):
    assert client.get(path, headers=as_user("asha")).status_code == 403


def test_reports_need_signing_in(client):
    assert client.get("/api/v1/reports/coverage").status_code == 401
    assert client.get("/api/v1/reports/coverage.csv").status_code == 401
