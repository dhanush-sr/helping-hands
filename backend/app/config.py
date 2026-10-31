"""Application settings, read from environment variables prefixed with ``HH_``.

Example: ``HH_ENVIRONMENT=test`` or a ``backend/.env`` file (not committed).
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HH_", env_file=".env", extra="ignore")

    app_name: str = "Helping Hands API"
    environment: str = "local"
    # Origins allowed to call the API from a browser (the Vite dev server by default).
    # Set as JSON in the environment, e.g. HH_CORS_ORIGINS='["https://example.org"]'.
    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
