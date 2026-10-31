"""HH-13 stores and busy periods: TC-STORE-01, TC-BP-01, manager rules and admin-only changes."""

from types import SimpleNamespace

import bcrypt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.db.session import get_db, make_engine
from app.main import create_app
from app.models import Base, BusyPeriod, Store, User, UserRole

PASSWORD = "Test@1234"

USERS = {
    "admin": UserRole.ADMIN,
    "meera": UserRole.STORE_MANAGER,
    "rahul": UserRole.STORE_MANAGER,
    "volunteer": UserRole.VOLUNTEER,
}


def fast_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=4)).decode()


@pytest.fixture
def world(tmp_path):
    """Two store managers, one inactive manager, and one existing store run by Meera."""
    engine = make_engine(f"sqlite:///{tmp_path / 'stores.db'}")
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
        users["former"] = User(
            email="former@example.org",
            full_name="Former Manager",
            password_hash=fast_hash(PASSWORD),
            role=UserRole.STORE_MANAGER,
            is_active=False,
        )
        koramangala = Store(name="Koramangala", location="80 Feet Road", manager=users["meera"])
        db.add_all([*users.values(), koramangala])
        db.commit()
        ids = SimpleNamespace(store=koramangala.id, **{n: u.id for n, u in users.items()})
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


def count(world, model) -> int:
    with world.sessions() as db:
        return db.scalar(select(func.count()).select_from(model))


# --- stores ----------------------------------------------------------------------------------


def test_admin_creates_a_store_with_a_manager(client, world, as_user):  # TC-STORE-01
    admin = as_user("admin")
    response = client.post(
        "/api/v1/stores",
        json={"name": "  Indiranagar ", "location": "100 Feet Road", "manager_id": world.ids.rahul},
        headers=admin,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Indiranagar"  # trimmed
    assert body["is_active"] is True
    assert body["manager"] == {
        "id": world.ids.rahul,
        "full_name": "Rahul",
        "email": "rahul@example.org",
    }
    names = [store["name"] for store in client.get("/api/v1/stores", headers=admin).json()]
    assert names == ["Indiranagar", "Koramangala"]


def test_store_can_start_without_a_manager(client, as_user):
    response = client.post(
        "/api/v1/stores",
        json={"name": "Jayanagar", "location": "4th Block"},
        headers=as_user("admin"),
    )
    assert response.status_code == 201
    assert response.json()["manager"] is None


def test_store_names_are_unique(client, world, as_user):
    response = client.post(
        "/api/v1/stores",
        json={"name": "Koramangala", "location": "Elsewhere"},
        headers=as_user("admin"),
    )
    assert response.status_code == 409
    assert response.json()["code"] == "STORE_NAME_TAKEN"
    assert count(world, Store) == 1


@pytest.mark.parametrize("who", ["volunteer", "former", "missing"])
def test_manager_must_be_an_active_store_manager(client, world, as_user, who):
    manager_id = 9999 if who == "missing" else getattr(world.ids, who)
    response = client.post(
        "/api/v1/stores",
        json={"name": "Whitefield", "location": "ITPL Road", "manager_id": manager_id},
        headers=as_user("admin"),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_MANAGER"
    assert count(world, Store) == 1


def test_admin_assigns_and_clears_the_manager(client, world, as_user):
    admin = as_user("admin")
    path = f"/api/v1/stores/{world.ids.store}"

    moved = client.patch(path, json={"manager_id": world.ids.rahul}, headers=admin)
    assert moved.status_code == 200
    assert moved.json()["manager"]["id"] == world.ids.rahul

    renamed = client.patch(path, json={"location": "New address"}, headers=admin)
    assert renamed.json()["manager"]["id"] == world.ids.rahul  # untouched when not sent

    cleared = client.patch(path, json={"manager_id": None}, headers=admin)
    assert cleared.json()["manager"] is None


def test_admin_deactivates_a_store(client, world, as_user):
    path = f"/api/v1/stores/{world.ids.store}"
    response = client.patch(path, json={"is_active": False}, headers=as_user("admin"))

    assert response.status_code == 200
    assert response.json()["is_active"] is False
    assert count(world, Store) == 1  # deactivated, not deleted
    # The manager no longer sees it in their list.
    assert client.get("/api/v1/stores", headers=as_user("meera")).json() == []


def test_renaming_to_a_taken_name_is_refused(client, world, as_user):
    admin = as_user("admin")
    client.post(
        "/api/v1/stores", json={"name": "Jayanagar", "location": "4th Block"}, headers=admin
    )
    response = client.patch(
        f"/api/v1/stores/{world.ids.store}", json={"name": "Jayanagar"}, headers=admin
    )
    assert response.status_code == 409


def test_unknown_store_is_404(client, as_user):
    response = client.patch("/api/v1/stores/999", json={"location": "x"}, headers=as_user("admin"))
    assert response.status_code == 404
    assert response.json()["code"] == "STORE_NOT_FOUND"


@pytest.mark.parametrize("name", ["meera", "volunteer"])
def test_only_admins_change_stores(client, world, as_user, name):
    headers = as_user(name)
    create = client.post(
        "/api/v1/stores", json={"name": "Hebbal", "location": "Outer Ring"}, headers=headers
    )
    change = client.patch(
        f"/api/v1/stores/{world.ids.store}", json={"is_active": False}, headers=headers
    )
    managers = client.get("/api/v1/store-managers", headers=headers)

    for response in (create, change, managers):
        assert response.status_code == 403
        assert response.json()["code"] == "FORBIDDEN"
    assert count(world, Store) == 1


def test_store_manager_sees_only_their_own_stores(client, as_user):
    assert [s["name"] for s in client.get("/api/v1/stores", headers=as_user("meera")).json()] == [
        "Koramangala"
    ]
    assert client.get("/api/v1/stores", headers=as_user("rahul")).json() == []


def test_volunteers_cannot_list_stores(client, as_user):
    assert client.get("/api/v1/stores", headers=as_user("volunteer")).status_code == 403


def test_store_manager_choices_are_active_store_managers(client, as_user):
    response = client.get("/api/v1/store-managers", headers=as_user("admin"))
    assert response.status_code == 200
    assert [m["full_name"] for m in response.json()] == ["Meera", "Rahul"]


# --- busy periods ----------------------------------------------------------------------------


def test_admin_defines_a_busy_period(client, world, as_user):  # TC-BP-01
    response = client.post(
        "/api/v1/busy-periods",
        json={"name": "Diwali weekend", "start_date": "2026-11-07", "end_date": "2026-11-08"},
        headers=as_user("admin"),
    )

    assert response.status_code == 201
    assert response.json() == {
        "id": 1,
        "name": "Diwali weekend",
        "start_date": "2026-11-07",
        "end_date": "2026-11-08",
    }


def test_one_day_busy_period_is_allowed(client, as_user):
    response = client.post(
        "/api/v1/busy-periods",
        json={"name": "Sale day", "start_date": "2026-11-20", "end_date": "2026-11-20"},
        headers=as_user("admin"),
    )
    assert response.status_code == 201


def test_end_before_start_is_rejected(client, world, as_user):
    response = client.post(
        "/api/v1/busy-periods",
        json={"name": "Backwards", "start_date": "2026-11-08", "end_date": "2026-11-07"},
        headers=as_user("admin"),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_DATE_RANGE"
    assert count(world, BusyPeriod) == 0


def test_busy_period_needs_a_name(client, as_user):
    response = client.post(
        "/api/v1/busy-periods",
        json={"name": "   ", "start_date": "2026-11-07", "end_date": "2026-11-08"},
        headers=as_user("admin"),
    )
    assert response.status_code == 422


@pytest.mark.parametrize("name", ["meera", "volunteer"])
def test_only_admins_define_busy_periods(client, world, as_user, name):
    response = client.post(
        "/api/v1/busy-periods",
        json={"name": "Weekend rush", "start_date": "2026-11-14", "end_date": "2026-11-15"},
        headers=as_user(name),
    )
    assert response.status_code == 403
    assert count(world, BusyPeriod) == 0


def test_everyone_signed_in_can_list_busy_periods_in_date_order(client, as_user):
    admin = as_user("admin")
    for name, start, end in [
        ("Weekend rush", "2026-11-14", "2026-11-15"),
        ("Diwali weekend", "2026-11-07", "2026-11-08"),
    ]:
        client.post(
            "/api/v1/busy-periods",
            json={"name": name, "start_date": start, "end_date": end},
            headers=admin,
        )

    for name in ("admin", "meera", "volunteer"):
        response = client.get("/api/v1/busy-periods", headers=as_user(name))
        assert response.status_code == 200
        assert [p["name"] for p in response.json()] == ["Diwali weekend", "Weekend rush"]

    assert client.get("/api/v1/busy-periods").status_code == 401  # not signed in
