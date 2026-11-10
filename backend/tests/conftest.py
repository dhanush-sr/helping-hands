import os

# The reminder job (HH-28) must not run during tests: they call the service directly with
# a fixed clock. Set before app.config is imported so the setting is read with it off.
os.environ.setdefault("HH_REMINDERS_ENABLED", "false")

import pytest
from sqlalchemy.orm import Session

from app.db.session import make_engine
from app.models import Base


@pytest.fixture
def db_session(tmp_path):
    """A fresh SQLite database with every table, created straight from the models."""
    engine = make_engine(f"sqlite:///{tmp_path / 'models.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()
