"""Shared fixtures: test API key env, live tracepulse_test DB, API client."""
import os
import sys
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP_DIR))

# Set before importing app modules (auth, database, notifications read env).
os.environ.setdefault("TRACEPULSE_API_KEY", "test-key")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/tracepulse_test",
)
os.environ.pop("SLACK_WEBHOOK_URL", None)  # never hit a real webhook from tests
os.environ.pop("EMAIL_IMAP_HOST", None)    # never start the email poller in tests

TEST_DB_URL = os.environ["DATABASE_URL"]


def _db_available() -> bool:
    try:
        import sqlalchemy
        eng = sqlalchemy.create_engine(TEST_DB_URL, connect_args={"connect_timeout": 2})
        with eng.connect():
            return True
    except Exception:
        return False


def pytest_collection_modifyitems(config, items):
    if _db_available():
        return
    skip = pytest.mark.skip(reason="live tracepulse_test DB not available")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def db_engine():
    from sqlalchemy import create_engine
    from models import Base
    eng = create_engine(TEST_DB_URL)
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)
    eng.dispose()


@pytest.fixture
def db_session(db_engine):
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()
    with db_engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE tickets, engineers, ingest_dedup RESTART IDENTITY CASCADE"
        ))


@pytest.fixture
def client(db_session):
    from database import get_db
    from main import app
    from fastapi.testclient import TestClient

    app.dependency_overrides[get_db] = lambda: db_session
    # No `with` block: lifespan (scheduler jobs) deliberately skipped in tests.
    yield TestClient(app, headers={"X-API-Key": "test-key"})
    app.dependency_overrides.clear()
