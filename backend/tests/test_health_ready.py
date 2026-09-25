import pytest
from fastapi.testclient import TestClient
from redis import Redis
from sqlalchemy import Engine, create_engine

from app.api.routes.health import get_redis
from app.db.session import get_engine
from app.main import create_app

# Nothing listens on port 1, so connections are refused immediately.
DEAD_REDIS = Redis(host="127.0.0.1", port=1, socket_connect_timeout=1)


def _client_with_engine(engine: Engine, redis: Redis | None = None) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_engine] = lambda: engine
    if redis is not None:
        app.dependency_overrides[get_redis] = lambda: redis
    return TestClient(app)


@pytest.mark.db
def test_ready_when_database_is_up(migrated_engine: Engine) -> None:
    with _client_with_engine(migrated_engine) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok", "redis": "ok"}}


@pytest.mark.db
def test_not_ready_when_redis_is_down(migrated_engine: Engine) -> None:
    with _client_with_engine(migrated_engine, DEAD_REDIS) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"] == {"database": "ok", "redis": "unavailable"}


def test_not_ready_when_database_is_down() -> None:
    # Nothing listens on port 1, so the connection is refused immediately.
    dead_engine = create_engine(
        "postgresql+psycopg://nobody:wrong@127.0.0.1:1/none", connect_args={"connect_timeout": 2}
    )

    with _client_with_engine(dead_engine, DEAD_REDIS) as client:
        response = client.get("/health/ready")
        liveness = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "checks": {"database": "unavailable", "redis": "unavailable"}}
    # Liveness must stay green: a database outage is not a reason to restart the API.
    assert liveness.status_code == 200
    dead_engine.dispose()
