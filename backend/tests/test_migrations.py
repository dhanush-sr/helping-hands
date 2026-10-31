"""The Alembic migration must build the whole schema from an empty database and remove it
again, on SQLite and (in CI) PostgreSQL."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from tests.helpers import database_urls

BACKEND_DIR = Path(__file__).resolve().parents[1]
CORE_TABLES = {
    "users", "stores", "busy_periods", "shifts", "signups", "settings", "auth_sessions",
}


def alembic_config(url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    config.attributes["configure_logger"] = False
    return config


def test_upgrade_from_empty_then_downgrade(tmp_path):
    for url in database_urls(tmp_path):
        config = alembic_config(url)
        command.downgrade(config, "base")  # no-op on an empty database
        command.upgrade(config, "head")

        engine = create_engine(url)
        try:
            inspector = inspect(engine)
            tables = set(inspector.get_table_names())
            assert CORE_TABLES <= tables, url

            unique_sets = {
                tuple(uq["column_names"]) for uq in inspector.get_unique_constraints("signups")
            }
            assert ("shift_id", "volunteer_id") in unique_sets, url

            with engine.connect() as connection:
                settings = dict(connection.execute(text("SELECT key, value FROM settings")).all())
            assert settings == {
                "weekly_hour_limit": 8,
                "min_notice_hours": 12,
                "withdrawal_cutoff_hours": 24,
            }, url
        finally:
            engine.dispose()

        command.downgrade(config, "base")

        engine = create_engine(url)
        try:
            assert not CORE_TABLES & set(inspect(engine).get_table_names()), url
        finally:
            engine.dispose()


def test_migration_rejects_bad_rows(tmp_path):
    """The CHECK constraints live in the migration, not only in the models."""
    url = database_urls(tmp_path)[0]
    command.upgrade(alembic_config(url), "head")
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (email, full_name, password_hash, role) "
                    "VALUES ('m@example.org', 'M', 'x', 'STORE_MANAGER')"
                )
            )
            connection.execute(text("INSERT INTO stores (name, location) VALUES ('S', 'L')"))

        bad_rows = [
            "INSERT INTO shifts (store_id, task, starts_at, ends_at, slots) "
            "VALUES (1, 't', '2026-11-07 10:00:00', '2026-11-07 09:00:00', 1)",
            "INSERT INTO shifts (store_id, task, starts_at, ends_at, slots) "
            "VALUES (1, 't', '2026-11-07 09:00:00', '2026-11-07 10:00:00', 0)",
            "INSERT INTO busy_periods (name, start_date, end_date) "
            "VALUES ('b', '2026-11-08', '2026-11-07')",
            "INSERT INTO users (email, full_name, password_hash, role) "
            "VALUES ('x@example.org', 'X', 'x', 'SUPERUSER')",
            "UPDATE settings SET value = 0 WHERE key = 'weekly_hour_limit'",
        ]
        for statement in bad_rows:
            with pytest.raises(IntegrityError), engine.begin() as connection:
                connection.execute(text(statement))
    finally:
        engine.dispose()
