from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """One engine (and connection pool) per process, created on first use."""
    return create_engine(
        get_settings().database_url(),
        # Check a pooled connection is alive before using it, so a database restart
        # doesn't turn into errors on the next few requests.
        pool_pre_ping=True,
        # Fail fast (seconds) when the database host is unreachable, instead of hanging.
        connect_args={"connect_timeout": 5},
    )


@lru_cache
def session_factory() -> sessionmaker[Session]:
    """Creates sessions bound to the app engine (also used by the CLI)."""
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed afterwards."""
    session = session_factory()()
    try:
        yield session
    finally:
        session.close()
