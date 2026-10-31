"""Shared test helpers."""

import os


def database_urls(tmp_path) -> list[str]:
    """SQLite always; PostgreSQL too when HH_TEST_DATABASE_URL is set (as it is in CI)."""
    urls = [f"sqlite:///{tmp_path / 'migrations.db'}"]
    postgres_url = os.getenv("HH_TEST_DATABASE_URL")
    if postgres_url:
        urls.append(postgres_url)
    return urls
