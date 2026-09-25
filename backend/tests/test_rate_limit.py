"""Rate limiting on login and register (with an in-memory counter instead of Redis)."""

import pytest
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core import rate_limit
from app.core.config import get_settings


class MemoryStore:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def incr_with_expiry(self, key: str, seconds: int) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]


class BrokenStore:
    def incr_with_expiry(self, key: str, seconds: int) -> int:
        raise RedisConnectionError("down")


@pytest.fixture
def limited(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    get_settings.cache_clear()
    store = MemoryStore()
    monkeypatch.setattr(rate_limit, "get_counter_store", lambda: store)
    return client


def test_login_is_blocked_after_10_tries_a_minute(limited: TestClient) -> None:
    body = {"email": "nobody@example.com", "password": "wrong-password"}
    # The login itself fails (no database needed): 401 means "not blocked yet".
    statuses = [limited.post("/api/v1/auth/login", json=body).status_code for _ in range(11)]

    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429
    blocked = limited.post("/api/v1/auth/login", json=body)
    assert blocked.headers["retry-after"] == "60"
    assert "Too many attempts" in blocked.json()["detail"]


def test_register_limit_is_separate_and_stricter(limited: TestClient) -> None:
    bad = {"email": "x", "password": "short", "full_name": ""}  # 422 = not blocked, just invalid
    statuses = [limited.post("/api/v1/auth/register", json=bad).status_code for _ in range(6)]

    assert statuses[:5] == [422] * 5 and statuses[5] == 429


def test_redis_down_does_not_lock_everyone_out(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    get_settings.cache_clear()
    monkeypatch.setattr(rate_limit, "get_counter_store", lambda: BrokenStore())

    for _ in range(15):
        assert client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "x"}).status_code == 401
