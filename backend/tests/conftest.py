from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.ai.dependencies import get_ai_service
from app.core.config import get_settings
from app.db.session import get_db, get_engine, session_factory
from app.main import create_app

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _clear_caches() -> None:
    get_settings.cache_clear()
    get_ai_service.cache_clear()
    get_engine.cache_clear()
    session_factory.cache_clear()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    # Fixed values so tests never depend on a developer's local .env file.
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173")
    _clear_caches()

    with TestClient(create_app()) as test_client:
        yield test_client

    _clear_caches()


# ---------- Database ----------


def alembic_config(engine: Engine) -> Config:
    """Alembic config aimed at the given engine's database (never the development one)."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["url"] = engine.url
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture(scope="session")
def test_engine() -> Iterator[Engine]:
    """Engine for the separate test database. Skips DB tests if it isn't running."""
    engine = create_engine(get_settings().database_url(test=True), pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError:
        engine.dispose()
        pytest.skip("Test database not reachable. Start it with: docker compose up -d")
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def migrated_engine(test_engine: Engine) -> Engine:
    """Test database with every migration applied: the same path production uses."""
    command.upgrade(alembic_config(test_engine), "head")
    return test_engine


@pytest.fixture
def db_session(migrated_engine: Engine) -> Iterator[Session]:
    """A session whose work is rolled back after each test, so tests never see each other's data.

    The app code calls commit(); with join_transaction_mode="create_savepoint" those commits
    only release savepoints inside our outer transaction, which is rolled back at the end.
    """
    connection = migrated_engine.connect()
    outer = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        autoflush=False,
        expire_on_commit=False,
    )
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


@pytest.fixture
def api(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Test client whose requests use the rolled-back test session."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173")
    # TestClient talks plain http://testserver; Secure cookies would never be sent back.
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    # Never put real jobs on Redis from tests. Triage tests switch it on with a fake queue.
    monkeypatch.setenv("AI_TRIAGE_ENABLED", "false")
    # Many tests log in many times from the same test client IP.
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    _clear_caches()

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client

    _clear_caches()


@pytest.fixture
def world(db_session: Session):
    from tests.helpers import build_world

    return build_world(db_session)
