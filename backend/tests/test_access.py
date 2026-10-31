"""HH-12 role and store checks: TC-AUTH-03, TC-AUTH-04, sign-up scope and deny by default.

Posting a shift uses the real endpoint (HH-15). Editing shifts and deciding or withdrawing
sign-ups arrive with HH-22, HH-24 and HH-26; until then these tests add small stand-in
endpoints to a copy of the app, wired the way the real ones must be (a ``require_*`` role
check plus the store-scope helpers). When a real endpoint lands, point its test here at it
and delete the stand-in.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import bcrypt
import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import (
    get_current_session,
    require_manager,
    require_manager_or_admin,
    require_role,
    require_volunteer,
    shift_in_scope,
    signup_in_scope,
)
from app.api.v1 import auth as auth_api
from app.api.v1 import health as health_api
from app.db.session import get_db, make_engine
from app.main import app as real_app
from app.main import create_app
from app.models import Base, Shift, SignUp, SignUpStatus, Store, User, UserRole
from app.services import access

PASSWORD = "Test@1234"
STARTS_AT = datetime(2026, 11, 8, 4, 30, tzinfo=UTC)  # 10:00 IST

# Endpoints anyone may call without signing in (GET /api/v1/health, POST /api/v1/auth/login).
# Everything else must check the role. Matched by function, so router prefixes don't matter.
PUBLIC_ENDPOINTS = {health_api.health, auth_api.login}

USERS = {
    "admin": UserRole.ADMIN,
    "manager_a": UserRole.STORE_MANAGER,
    "manager_b": UserRole.STORE_MANAGER,
    "volunteer": UserRole.VOLUNTEER,
    "other_volunteer": UserRole.VOLUNTEER,
}


# --- stand-in endpoints, shaped like SAD 4.3 -----------------------------------------------


class ShiftEdit(BaseModel):
    slots: int = Field(ge=1)


class Decision(BaseModel):
    decision: str = Field(pattern="^(APPROVE|DECLINE)$")


def stand_in_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.patch("/shifts/{shift_id}", dependencies=[Depends(require_manager)])
    def edit_shift(
        body: ShiftEdit, shift: Shift = Depends(shift_in_scope), db: Session = Depends(get_db)
    ) -> dict:
        shift.slots = body.slots
        db.commit()
        return {"shiftId": shift.id, "slots": shift.slots}

    @router.patch("/signups/{signup_id}")
    def decide_signup(
        body: Decision,
        user: User = Depends(require_manager),
        signup: SignUp = Depends(signup_in_scope),
        db: Session = Depends(get_db),
    ) -> dict:
        approved = body.decision == "APPROVE"
        signup.status = SignUpStatus.CONFIRMED if approved else SignUpStatus.DECLINED
        signup.decided_by_id = user.id
        db.commit()
        return {"signUpId": signup.id, "status": signup.status.value}

    @router.post("/signups/{signup_id}/withdraw", dependencies=[Depends(require_volunteer)])
    def withdraw_signup(
        signup: SignUp = Depends(signup_in_scope), db: Session = Depends(get_db)
    ) -> dict:
        signup.status = SignUpStatus.WITHDRAWN
        db.commit()
        return {"signUpId": signup.id, "status": signup.status.value}

    @router.get("/stores/{store_id}/coverage")
    def store_coverage(
        store_id: int,
        user: User = Depends(require_manager_or_admin),
        db: Session = Depends(get_db),
    ) -> dict:
        store = access.get_store_in_scope(db, user, store_id)
        return {"storeId": store.id, "shifts": len(store.shifts)}

    return router


def build_app() -> FastAPI:
    app = create_app()
    app.include_router(stand_in_router())
    return app


# --- fixtures --------------------------------------------------------------------------------


def fast_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=4)).decode()


@pytest.fixture
def world(tmp_path):
    """Store A (manager_a) and store B (manager_b); B has a shift with one sign-up."""
    engine = make_engine(f"sqlite:///{tmp_path / 'access.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        users = {
            name: User(
                email=f"{name}@example.org",
                full_name=name.replace("_", " ").title(),
                password_hash=fast_hash(PASSWORD),
                role=role,
            )
            for name, role in USERS.items()
        }
        store_a = Store(name="Store A", location="A Road", manager=users["manager_a"])
        store_b = Store(name="Store B", location="B Road", manager=users["manager_b"])
        shift_b = Shift(
            store=store_b,
            task="Billing counter",
            starts_at=STARTS_AT,
            ends_at=STARTS_AT + timedelta(hours=4),
            slots=2,
        )
        signup_b = SignUp(shift=shift_b, volunteer=users["volunteer"])
        db.add_all([*users.values(), store_a, store_b, shift_b, signup_b])
        db.commit()
        ids = SimpleNamespace(
            store_a=store_a.id, store_b=store_b.id, shift_b=shift_b.id, signup_b=signup_b.id
        )
    yield SimpleNamespace(sessions=factory, ids=ids)
    engine.dispose()


@pytest.fixture
def client(world):
    def override_get_db():
        with world.sessions() as db:
            yield db

    app = build_app()
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


@pytest.fixture
def as_user(client):
    """``as_user("manager_a")`` signs that user in and returns their auth header."""

    def sign_in(name: str) -> dict[str, str]:
        response = client.post(
            "/api/v1/auth/login", json={"email": f"{name}@example.org", "password": PASSWORD}
        )
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return sign_in


def new_shift_body(store_id: int) -> dict:
    """A valid POST /api/v1/shifts body (SAD format), always a week in the future."""
    return {
        "storeId": store_id,
        "date": (datetime.now(UTC) + timedelta(days=7)).date().isoformat(),
        "startTime": "14:00",
        "endTime": "18:00",
        "task": "Restocking shelves",
        "slotsNeeded": 3,
    }


def shift_count(world) -> int:
    with world.sessions() as db:
        return db.scalar(select(func.count()).select_from(Shift))


def stored(world, model, item_id):
    with world.sessions() as db:
        return db.get(model, item_id)


FORBIDDEN = {"code": "FORBIDDEN", "message": "You don't have permission to do this."}
STORE_FORBIDDEN = {
    "code": "STORE_FORBIDDEN",
    "message": "You can only manage your own store's shifts and sign-ups.",
}


# --- role checks -----------------------------------------------------------------------------


def test_volunteer_cannot_post_a_shift(client, world, as_user):  # TC-AUTH-03
    before = shift_count(world)

    response = client.post(
        "/api/v1/shifts", json=new_shift_body(world.ids.store_a), headers=as_user("volunteer")
    )

    assert response.status_code == 403
    assert response.json() == FORBIDDEN
    assert shift_count(world) == before  # nothing saved


def test_role_is_checked_before_the_input(client, as_user):
    # A volunteer learns nothing about the endpoint, not even what input it expects.
    response = client.post("/api/v1/shifts", json={}, headers=as_user("volunteer"))
    assert response.status_code == 403
    assert response.json() == FORBIDDEN


@pytest.mark.parametrize("name", ["volunteer", "admin"])
def test_only_store_managers_post_shifts(client, world, as_user, name):
    # SAD 4.3: POST /shifts is for STORE_MANAGER only.
    response = client.post(
        "/api/v1/shifts", json=new_shift_body(world.ids.store_b), headers=as_user(name)
    )
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


def test_store_manager_posts_a_shift_for_their_own_store(client, world, as_user):
    before = shift_count(world)
    response = client.post(
        "/api/v1/shifts", json=new_shift_body(world.ids.store_a), headers=as_user("manager_a")
    )
    assert response.status_code == 201
    assert shift_count(world) == before + 1


def test_volunteer_cannot_call_a_manager_or_admin_endpoint(client, world, as_user):
    path = f"/api/v1/stores/{world.ids.store_a}/coverage"
    response = client.get(path, headers=as_user("volunteer"))
    assert response.status_code == 403
    assert response.json() == FORBIDDEN


def test_role_check_still_needs_a_signed_in_user(client, world):
    response = client.post("/api/v1/shifts", json=new_shift_body(world.ids.store_a))
    assert response.status_code == 401
    assert response.json()["code"] == "NOT_AUTHENTICATED"


def test_require_role_needs_at_least_one_role():
    with pytest.raises(ValueError):
        require_role()


# --- store scope -----------------------------------------------------------------------------


def test_manager_cannot_edit_another_stores_shift(client, world, as_user):  # TC-AUTH-04
    response = client.patch(
        f"/api/v1/shifts/{world.ids.shift_b}", json={"slots": 9}, headers=as_user("manager_a")
    )

    assert response.status_code == 403
    assert response.json() == STORE_FORBIDDEN
    assert stored(world, Shift, world.ids.shift_b).slots == 2  # shift unchanged


def test_manager_edits_their_own_stores_shift(client, world, as_user):
    response = client.patch(
        f"/api/v1/shifts/{world.ids.shift_b}", json={"slots": 3}, headers=as_user("manager_b")
    )
    assert response.status_code == 200
    assert stored(world, Shift, world.ids.shift_b).slots == 3


def test_manager_cannot_post_a_shift_for_another_store(client, world, as_user):
    before = shift_count(world)
    response = client.post(
        "/api/v1/shifts", json=new_shift_body(world.ids.store_b), headers=as_user("manager_a")
    )
    assert response.status_code == 403
    assert response.json() == STORE_FORBIDDEN
    assert shift_count(world) == before


def test_manager_cannot_decide_another_stores_signup(client, world, as_user):
    response = client.patch(
        f"/api/v1/signups/{world.ids.signup_b}",
        json={"decision": "APPROVE"},
        headers=as_user("manager_a"),
    )
    assert response.status_code == 403
    assert response.json() == STORE_FORBIDDEN
    assert stored(world, SignUp, world.ids.signup_b).status == SignUpStatus.REQUESTED


def test_manager_decides_their_own_stores_signup(client, world, as_user):
    response = client.patch(
        f"/api/v1/signups/{world.ids.signup_b}",
        json={"decision": "APPROVE"},
        headers=as_user("manager_b"),
    )
    assert response.status_code == 200
    assert stored(world, SignUp, world.ids.signup_b).status == SignUpStatus.CONFIRMED


def test_volunteer_cannot_withdraw_someone_elses_signup(client, world, as_user):
    path = f"/api/v1/signups/{world.ids.signup_b}/withdraw"
    response = client.post(path, headers=as_user("other_volunteer"))
    assert response.status_code == 403
    assert response.json() == {
        "code": "FORBIDDEN",
        "message": "You can only change your own sign-ups.",
    }
    assert stored(world, SignUp, world.ids.signup_b).status == SignUpStatus.REQUESTED

    assert client.post(path, headers=as_user("volunteer")).status_code == 200
    assert stored(world, SignUp, world.ids.signup_b).status == SignUpStatus.WITHDRAWN


def test_admin_works_across_stores_where_the_role_allows(client, world, as_user):
    admin = as_user("admin")
    for store_id in (world.ids.store_a, world.ids.store_b):
        response = client.get(f"/api/v1/stores/{store_id}/coverage", headers=admin)
        assert response.status_code == 200

    path = f"/api/v1/stores/{world.ids.store_b}/coverage"
    assert client.get(path, headers=as_user("manager_a")).status_code == 403
    assert client.get(path, headers=as_user("manager_b")).status_code == 200


def test_scope_follows_the_current_store_manager(client, world, as_user):
    # Checked against the database on every request, so reassigning a store takes effect now.
    with world.sessions() as db:
        db.get(Store, world.ids.store_b).manager_id = None
        db.commit()
    response = client.patch(
        f"/api/v1/shifts/{world.ids.shift_b}", json={"slots": 3}, headers=as_user("manager_b")
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    ("method", "path", "body", "code"),
    [
        ("PATCH", "/api/v1/shifts/999", {"slots": 1}, "SHIFT_NOT_FOUND"),
        ("PATCH", "/api/v1/signups/999", {"decision": "APPROVE"}, "SIGNUP_NOT_FOUND"),
        ("POST", "/api/v1/shifts", new_shift_body(999), "STORE_NOT_FOUND"),
    ],
)
def test_unknown_ids_give_404(client, as_user, method, path, body, code):
    response = client.request(method, path, json=body, headers=as_user("manager_a"))
    assert response.status_code == 404
    assert response.json()["code"] == code


def test_unknown_id_is_still_403_for_the_wrong_role(client, as_user):
    response = client.patch("/api/v1/shifts/999", json={"slots": 1}, headers=as_user("volunteer"))
    assert response.status_code == 403


# --- deny by default -------------------------------------------------------------------------


def dependency_calls(dependant) -> list:
    calls = []
    for sub in dependant.dependencies:
        calls.append(sub.call)
        calls.extend(dependency_calls(sub))
    return calls


def api_routes(routes) -> list[APIRoute]:
    """Every endpoint, including those in included routers.

    Newer FastAPI versions wrap each included router (it keeps the router in
    ``original_router``) instead of copying its routes onto the app, so walk into those.
    /docs and /openapi.json are plain Starlette routes and are skipped.
    """
    found = []
    for route in routes:
        if isinstance(route, APIRoute):
            found.append(route)
        inner = getattr(route, "original_router", None)
        if inner is not None:
            found.extend(api_routes(inner.routes))
    return found


def unguarded_routes(app: FastAPI) -> list[str]:
    """Routes, other than the public ones, that skip sign-in or don't name their roles."""
    problems = []
    for route in api_routes(app.routes):
        if route.endpoint in PUBLIC_ENDPOINTS:
            continue
        calls = dependency_calls(route.dependant)
        for method in sorted(route.methods):
            if get_current_session not in calls:
                problems.append(f"{method} {route.path}: no sign-in check")
            elif not any(hasattr(call, "allowed_roles") for call in calls):
                problems.append(f"{method} {route.path}: no require_role(...) check")
    return problems


def test_every_endpoint_checks_sign_in_and_role():
    # Fails as soon as someone adds an endpoint without a role check (HH-SR-004).
    assert unguarded_routes(real_app) == []
    assert unguarded_routes(build_app()) == []


def test_the_route_check_sees_every_endpoint():
    # Guards the check itself: if the walk found no routes, the test above would pass
    # without checking anything.
    endpoints = {route.endpoint for route in api_routes(real_app.routes)}
    assert PUBLIC_ENDPOINTS <= endpoints  # the public list is not stale
    assert {auth_api.logout, auth_api.me} <= endpoints


def test_the_route_check_catches_an_unguarded_endpoint():
    app = FastAPI()

    @app.get("/api/v1/open")
    def open_endpoint() -> dict:
        return {}

    @app.get("/api/v1/signed-in-only")
    def signed_in_only(session=Depends(get_current_session)) -> dict:
        return {}

    assert unguarded_routes(app) == [
        "GET /api/v1/open: no sign-in check",
        "GET /api/v1/signed-in-only: no require_role(...) check",
    ]


# --- error shape -----------------------------------------------------------------------------


def test_framework_errors_use_the_same_shape(client, world, as_user):
    not_found = client.get("/api/v1/does-not-exist")
    assert not_found.status_code == 404
    assert not_found.json() == {"code": "NOT_FOUND", "message": "Not Found"}

    wrong_method = client.delete("/api/v1/health")
    assert wrong_method.status_code == 405
    assert wrong_method.json()["code"] == "METHOD_NOT_ALLOWED"

    bad_input = client.patch(
        f"/api/v1/shifts/{world.ids.shift_b}", json={"slots": 0}, headers=as_user("manager_b")
    )
    assert bad_input.status_code == 422
    assert bad_input.json()["code"] == "VALIDATION_ERROR"
    assert "slots" in bad_input.json()["message"]


def test_invalid_input_is_not_echoed_back(client):
    too_long = "hunter2-secret" * 10  # over the 128-character limit, so it fails validation
    response = client.post("/api/v1/auth/login", json={"email": "x", "password": too_long})
    assert response.status_code == 422
    assert set(response.json()) == {"code", "message"}
    assert "hunter2-secret" not in response.text
