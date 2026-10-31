"""HH-11 sign in and out: TC-AUTH-01, TC-AUTH-02, lockout, idle timeout and sign-out."""

import logging
from datetime import UTC, datetime, timedelta

import bcrypt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app import security
from app.db.session import get_db, make_engine
from app.main import app
from app.models import AuthSession, Base, User, UserRole

PASSWORD = "Volunteer@123"


def fast_hash(password: str) -> str:
    # Low bcrypt cost keeps the tests quick; the app itself uses the default cost.
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=4)).decode()


@pytest.fixture
def sessions(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'auth.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        db.add_all(
            [
                User(
                    email="volunteer@example.org",
                    full_name="Asha Volunteer",
                    password_hash=fast_hash(PASSWORD),
                    role=UserRole.VOLUNTEER,
                ),
                User(
                    email="former@example.org",
                    full_name="Former Staff",
                    password_hash=fast_hash(PASSWORD),
                    role=UserRole.VOLUNTEER,
                    is_active=False,
                ),
            ]
        )
        db.commit()
    yield factory
    engine.dispose()


@pytest.fixture
def client(sessions):
    def override_get_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def clock(monkeypatch):
    """Lets a test move time forward. Starts at the real time so token expiry still works."""
    state = {"now": datetime.now(UTC)}
    monkeypatch.setattr(security, "utcnow", lambda: state["now"])
    return state


def login(client, email="volunteer@example.org", password=PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def test_sign_in_returns_a_token_that_works(client):  # TC-AUTH-01
    response = login(client)

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["idle_timeout_minutes"] == 30
    assert body["user"] == {
        "id": 1,
        "email": "volunteer@example.org",
        "full_name": "Asha Volunteer",
        "role": "VOLUNTEER",
    }
    me = client.get("/api/v1/auth/me", headers=auth_header(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["email"] == "volunteer@example.org"


def test_email_is_not_case_sensitive(client):
    assert login(client, email="  Volunteer@Example.ORG ").status_code == 200


def test_wrong_password_and_unknown_email_look_the_same(client):  # TC-AUTH-02
    wrong_password = login(client, password="not-it")
    unknown_email = login(client, email="nobody@example.org")

    expected = {"code": "INVALID_CREDENTIALS", "message": "Incorrect email or password."}
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json() == expected


def test_account_locks_after_five_wrong_passwords(client, clock):
    for _ in range(5):
        assert login(client, password="wrong").status_code == 401

    locked = login(client)  # even the right password is refused while locked
    assert locked.status_code == 423
    assert locked.json()["code"] == "ACCOUNT_LOCKED"

    clock["now"] += timedelta(minutes=14)
    assert login(client).status_code == 423
    clock["now"] += timedelta(minutes=2)
    assert login(client).status_code == 200


def test_a_successful_sign_in_resets_the_failed_count(client, sessions):
    for _ in range(4):
        login(client, password="wrong")
    assert login(client).status_code == 200
    with sessions() as db:
        user = db.scalar(select(User).where(User.email == "volunteer@example.org"))
        assert user.failed_login_attempts == 0
        assert user.last_login_at is not None


def test_deactivated_account_cannot_sign_in(client):
    response = login(client, email="former@example.org")
    assert response.status_code == 403
    assert response.json()["code"] == "ACCOUNT_DISABLED"


def test_session_ends_after_30_minutes_idle(client, clock):
    token = login(client).json()["access_token"]

    clock["now"] += timedelta(minutes=29)
    assert client.get("/api/v1/auth/me", headers=auth_header(token)).status_code == 200

    # Activity resets the idle timer, so 29 more minutes is still fine...
    clock["now"] += timedelta(minutes=29)
    assert client.get("/api/v1/auth/me", headers=auth_header(token)).status_code == 200

    # ...but 31 minutes with no request ends the session for good.
    clock["now"] += timedelta(minutes=31)
    expired = client.get("/api/v1/auth/me", headers=auth_header(token))
    assert expired.status_code == 401
    assert expired.json()["code"] == "SESSION_EXPIRED"
    assert client.get("/api/v1/auth/me", headers=auth_header(token)).status_code == 401


def test_sign_out_ends_the_session(client, sessions):
    token = login(client).json()["access_token"]

    assert client.post("/api/v1/auth/logout", headers=auth_header(token)).status_code == 204
    after = client.get("/api/v1/auth/me", headers=auth_header(token))
    assert after.status_code == 401
    assert after.json()["code"] == "NOT_AUTHENTICATED"
    with sessions() as db:
        assert db.scalar(select(AuthSession)).revoked_at is not None


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer not-a-token"}, {"Authorization": "Basic abc"}],
)
def test_protected_endpoint_needs_a_valid_token(client, headers):
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 401
    assert response.json()["code"] == "NOT_AUTHENTICATED"
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_tampered_token_is_rejected(client):
    token = login(client).json()["access_token"]
    tampered = token[:-2] + ("AA" if not token.endswith("AA") else "BB")
    assert client.get("/api/v1/auth/me", headers=auth_header(tampered)).status_code == 401


def test_password_hash_is_bcrypt():
    password_hash = security.hash_password(PASSWORD)
    assert password_hash.startswith("$2") and PASSWORD not in password_hash
    assert security.verify_password(PASSWORD, password_hash)
    assert not security.verify_password("other", password_hash)


def test_passwords_and_tokens_are_not_logged(client, caplog):
    caplog.set_level(logging.DEBUG)
    token = login(client).json()["access_token"]
    login(client, password="wrong-secret")
    client.get("/api/v1/auth/me", headers=auth_header(token))

    assert PASSWORD not in caplog.text
    assert "wrong-secret" not in caplog.text
    assert token not in caplog.text
