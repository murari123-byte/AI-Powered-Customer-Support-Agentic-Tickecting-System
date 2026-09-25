from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.ai.dependencies import get_ai_service
from app.ai.service import AIService
from app.ai.types import ProviderHealth
from app.main import create_app
from tests.fakes import FakeLLMProvider


@pytest.fixture
def client_with(monkeypatch: pytest.MonkeyPatch) -> Iterator:
    """Build a test client whose AI service uses a fake provider with the given health."""
    clients: list[TestClient] = []

    def _make(health: ProviderHealth) -> TestClient:
        app = create_app()
        service = AIService(FakeLLMProvider(health=health))
        app.dependency_overrides[get_ai_service] = lambda: service
        client = TestClient(app)
        clients.append(client)
        return client

    yield _make
    for client in clients:
        client.close()


def test_ai_health_ok(client_with) -> None:
    client = client_with(ProviderHealth(reachable=True, models={"fake-chat": True, "fake-embed": True}))

    response = client.get("/health/ai")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "provider": "fake",
        "chat_model": "fake-chat",
        "embed_model": "fake-embed",
        "models": {"fake-chat": True, "fake-embed": True},
        "detail": None,
    }


def test_ai_health_503_when_model_missing(client_with) -> None:
    client = client_with(
        ProviderHealth(
            reachable=True,
            models={"fake-chat": True, "fake-embed": False},
            detail="Model not downloaded: fake-embed",
        )
    )

    response = client.get("/health/ai")

    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert response.json()["detail"] == "Model not downloaded: fake-embed"


def test_ai_health_503_when_server_down(client_with) -> None:
    client = client_with(ProviderHealth(reachable=False, models={"fake-chat": False, "fake-embed": False}))

    assert client.get("/health/ai").status_code == 503


def test_api_health_stays_ok_when_ai_is_down(client_with) -> None:
    client = client_with(ProviderHealth(reachable=False, models={"fake-chat": False, "fake-embed": False}))

    assert client.get("/health").status_code == 200
