"""HH-19: settings and app behaviour the Docker image and test environment rely on."""

import pytest
from fastapi.testclient import TestClient

from app import config
from app.config import Settings
from app.main import create_app


@pytest.fixture
def fresh_settings(monkeypatch):
    """Lets a test set HH_* variables and have create_app() read them."""
    config.get_settings.cache_clear()
    yield monkeypatch
    config.get_settings.cache_clear()


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("postgres://u:p@db.example:5432/hh", "postgresql+psycopg://u:p@db.example:5432/hh"),
        ("postgresql://u:p@db.example/hh?sslmode=require",
         "postgresql+psycopg://u:p@db.example/hh?sslmode=require"),
        ("postgresql+psycopg://u:p@db.example/hh", "postgresql+psycopg://u:p@db.example/hh"),
        ("sqlite:///./helping_hands.db", "sqlite:///./helping_hands.db"),
    ],
)
def test_hosted_database_urls_use_the_psycopg_driver(given, expected):
    assert Settings(database_url=given).database_url == expected


def test_health_reports_the_commit(fresh_settings):
    fresh_settings.setenv("HH_COMMIT", "abc123def456")
    fresh_settings.setenv("HH_ENVIRONMENT", "test")
    client = TestClient(create_app())

    body = client.get("/api/v1/health").json()

    assert body["status"] == "ok"
    assert body["commit"] == "abc123def456"
    assert body["environment"] == "test"


def test_built_frontend_is_served_next_to_the_api(fresh_settings, tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>Helping Hands</title>")
    fresh_settings.setenv("HH_FRONTEND_DIST", str(tmp_path))
    client = TestClient(create_app())

    page = client.get("/")
    assert page.status_code == 200
    assert "Helping Hands" in page.text

    # The API still wins, and its errors keep the JSON shape.
    assert client.get("/api/v1/health").json()["status"] == "ok"
    missing = client.get("/api/v1/does-not-exist")
    assert missing.status_code == 404
    assert missing.json()["code"] == "NOT_FOUND"


def test_no_frontend_is_served_when_not_configured(fresh_settings):
    fresh_settings.delenv("HH_FRONTEND_DIST", raising=False)
    client = TestClient(create_app())

    assert client.get("/").status_code == 404
