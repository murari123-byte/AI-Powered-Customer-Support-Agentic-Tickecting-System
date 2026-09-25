"""Prometheus metrics: the endpoint, safe labels, and the business counters."""

import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY
from sqlalchemy.orm import Session

from tests.helpers import World, auth


def value(name: str, **labels) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def test_metrics_endpoint_uses_route_templates_not_ids(client: TestClient) -> None:
    client.get("/api/v1/tickets/3f2a0000-0000-0000-0000-000000000000")  # 401, but still counted
    client.get("/some/random/scanner/path")

    body = client.get("/metrics").text

    assert 'route="/api/v1/tickets/{ticket_id}"' in body
    assert "3f2a0000" not in body  # a real id would create a new series per ticket
    assert 'route="unmatched",status="404"' in body
    assert 'route="/metrics"' not in body  # the scrape itself isn't counted


def test_metric_families_exist(client: TestClient) -> None:
    body = client.get("/metrics").text

    for name in [
        "http_requests_total",
        "http_request_duration_seconds",
        "ai_call_duration_seconds",
        "rag_answers_total",
        "tickets_created_total",
        "ticket_escalations_total",
        "celery_tasks_total",
    ]:
        assert f"# TYPE {name}" in body


@pytest.mark.db
def test_ticket_and_escalation_counters(api: TestClient, db_session: Session, world: World) -> None:
    created_before = value("tickets_created_total")
    escalated_before = value("ticket_escalations_total", source="person")

    ticket = world.new_ticket(db_session)
    ticket.team_id = world.billing.id
    db_session.commit()
    api.post(
        f"/api/v1/tickets/{ticket.id}/escalate", json={"reason": "angry customer"}, headers=auth(world.billing_agent)
    )

    assert value("tickets_created_total") == created_before + 1
    assert value("ticket_escalations_total", source="person") == escalated_before + 1


def test_ai_errors_are_counted() -> None:
    from app.ai.errors import AIUnavailableError
    from app.ai.service import AIService
    from tests.fakes import FakeLLMProvider

    before = value("ai_call_errors_total", purpose="text", error="AIUnavailableError")
    service = AIService(FakeLLMProvider([AIUnavailableError("down")]))

    with pytest.raises(AIUnavailableError):
        service.generate_text(system_prompt="s", user_prompt="u")

    assert value("ai_call_errors_total", purpose="text", error="AIUnavailableError") == before + 1
