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
