"""Application settings, read from environment variables prefixed with ``HH_``.

Example: ``HH_ENVIRONMENT=test`` or a ``backend/.env`` file (not committed).
"""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HH_", env_file=".env", extra="ignore")

    app_name: str = "Helping Hands API"
    environment: str = "local"
    # Git commit the running build came from; the Docker image sets it (HH-19), so the
    # deploy pipeline can tell when the test environment is on the new version.
    commit: str = "local"
    # SQLite file for local work; PostgreSQL elsewhere, e.g.
    # HH_DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/helping_hands
    database_url: str = "sqlite:///./helping_hands.db"
    # Origins allowed to call the API from a browser (the Vite dev server by default).
    # Set as JSON in the environment, e.g. HH_CORS_ORIGINS='["https://example.org"]'.
    cors_origins: list[str] = ["http://localhost:5173"]

    # Sign-in (HH-11). The default key is for local development only: set HH_SECRET_KEY
    # to a long random value in every shared or deployed environment.
    secret_key: str = "dev-only-secret-key-change-me-before-deploying"
    session_idle_minutes: int = 30  # signed out after this long without a request
    session_max_hours: int = 12  # hard limit on one session, even when active
    max_failed_logins: int = 5  # wrong passwords in a row before the account locks
    lockout_minutes: int = 15

    # Built frontend (``frontend/dist``) to serve from the same server, as the Docker image
    # does (HH-19). Unset in local development, where Vite serves the frontend.
    frontend_dist: str | None = None

    @field_validator("database_url")
    @classmethod
    def _use_psycopg_driver(cls, url: str) -> str:
        """Hosts hand out ``postgres://`` or ``postgresql://`` URLs; SQLAlchemy needs the
        psycopg 3 driver named, so those are rewritten to ``postgresql+psycopg://``."""
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix) :]
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
