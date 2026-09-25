"""Teams and tickets through the API: who sees what, conversation, status, assignment, escalation."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TicketEscalation, TicketStatus
from tests.helpers import World, auth

pytestmark = pytest.mark.db

TICKETS = "/api/v1/tickets"
TEAMS = "/api/v1/teams"


def in_team(db: Session, ticket, team, status: TicketStatus = TicketStatus.OPEN):
    ticket.team_id = team.id
    ticket.status = status
    db.commit()
    return ticket


# ---------- Teams ----------


def test_staff_see_teams_customers_dont(api: TestClient, world: World) -> None:
    teams = api.get(TEAMS, headers=auth(world.billing_agent)).json()

    assert [t["name"] for t in teams] == ["Billing Team", "Technical Support"]
    assert api.get(TEAMS, headers=auth(world.customer)).status_code == 403


def test_admin_manages_teams(api: TestClient, world: World) -> None:
    admin = auth(world.admin)

    created = api.post(TEAMS, json={"name": "Security"}, headers=admin)
    assert created.status_code == 201
    team_id = created.json()["id"]
    added = api.post(f"{TEAMS}/{team_id}/members", json={"user_id": str(world.tech_agent.id)}, headers=admin)
    assert [m["user"]["full_name"] for m in added.json()["members"]] == ["Tess Agent"]
    assert api.delete(f"{TEAMS}/{team_id}/members/{world.tech_agent.id}", headers=admin).status_code == 204


def test_team_rules(api: TestClient, world: World) -> None:
    assert api.post(TEAMS, json={"name": "Security"}, headers=auth(world.manager)).status_code == 403
    assert api.post(TEAMS, json={"name": "billing team"}, headers=auth(world.admin)).status_code == 409
    customer_joins = api.post(
        f"{TEAMS}/{world.tech.id}/members", json={"user_id": str(world.customer.id)}, headers=auth(world.admin)
    )
    assert customer_joins.status_code == 400


# ---------- Create and see tickets ----------


def test_customer_creates_ticket(api: TestClient, world: World) -> None:
    body = {"subject": "Charged twice", "description": "I paid 500 twice", "category": "BILLING"}

    response = api.post(TICKETS, json=body, headers=auth(world.customer))

    assert response.status_code == 201
    ticket = response.json()
    assert (ticket["status"], ticket["priority"], ticket["category"]) == ("OPEN", "MEDIUM", "BILLING")
    assert ticket["number"] >= 1001
    messages = api.get(f"{TICKETS}/{ticket['id']}/messages", headers=auth(world.customer)).json()
    assert [m["body"] for m in messages] == ["I paid 500 twice"]


def test_ticket_input_is_validated(api: TestClient, world: World) -> None:
    headers = auth(world.customer)

    assert api.post(TICKETS, json={"subject": "Hi", "description": "x"}, headers=headers).status_code == 422
    with_priority = {"subject": "Urgent", "description": "x", "priority": "CRITICAL"}
    assert api.post(TICKETS, json=with_priority, headers=headers).status_code == 422
    assert (
        api.post(TICKETS, json={"subject": "Hello", "description": "x"}, headers=auth(world.billing_agent)).status_code
        == 403
    )


def test_who_sees_which_tickets(api: TestClient, db_session: Session, world: World) -> None:
    in_team(db_session, world.new_ticket(db_session, "billing ticket"), world.billing)
    in_team(db_session, world.new_ticket(db_session, "tech ticket", world.other_customer), world.tech)
    world.new_ticket(db_session, "no team yet")

    def subjects(user) -> set[str]:
        return {t["subject"] for t in api.get(TICKETS, headers=auth(user)).json()["items"]}

    assert subjects(world.customer) == {"billing ticket", "no team yet"}
    assert subjects(world.other_customer) == {"tech ticket"}
    assert subjects(world.billing_agent) == {"billing ticket"}
    assert subjects(world.tech_agent) == {"tech ticket"}
    assert subjects(world.manager) == {"billing ticket", "tech ticket", "no team yet"}


def test_someone_elses_ticket_is_404(api: TestClient, db_session: Session, world: World) -> None:
    ticket = world.new_ticket(db_session)
    url = f"{TICKETS}/{ticket.id}"
    stranger = auth(world.other_customer)

    assert api.get(url, headers=stranger).status_code == 404
    assert api.get(f"{url}/messages", headers=stranger).status_code == 404
    assert api.post(f"{url}/messages", json={"body": "hi"}, headers=stranger).status_code == 404
    assert api.post(f"{url}/status", json={"status": "CLOSED"}, headers=stranger).status_code == 404


def test_filters_and_search(api: TestClient, db_session: Session, world: World) -> None:
    refund = world.new_ticket(db_session, "Refund not received")
    world.new_ticket(db_session, "Cannot log in")
    refund.priority = "HIGH"
    db_session.commit()
    headers = auth(world.customer)

    assert [t["subject"] for t in api.get(TICKETS, params={"search": "REFUND"}, headers=headers).json()["items"]] == [
        "Refund not received"
    ]
    assert api.get(TICKETS, params={"priority": "HIGH"}, headers=headers).json()["total"] == 1
    assert api.get(TICKETS, params={"search": "%"}, headers=headers).json()["total"] == 0
    newest_first = [t["subject"] for t in api.get(TICKETS, headers=headers).json()["items"]]
    assert newest_first == ["Cannot log in", "Refund not received"]


def test_staff_edit_priority_customers_cannot(api: TestClient, db_session: Session, world: World) -> None:
    ticket = in_team(db_session, world.new_ticket(db_session), world.billing)
    url = f"{TICKETS}/{ticket.id}"

    assert api.patch(url, json={"priority": "HIGH"}, headers=auth(world.billing_agent)).json()["priority"] == "HIGH"
    assert api.patch(url, json={"priority": "LOW"}, headers=auth(world.customer)).status_code == 403


# ---------- Conversation ----------


def test_internal_notes_are_hidden_from_customers(api: TestClient, db_session: Session, world: World) -> None:
    ticket = in_team(db_session, world.new_ticket(db_session), world.billing)
    url = f"{TICKETS}/{ticket.id}/messages"
    agent = auth(world.billing_agent)

    api.post(url, json={"body": "Checking now"}, headers=agent)
    api.post(url, json={"body": "Gateway bug", "is_internal": True}, headers=agent)

    assert [m["body"] for m in api.get(url, headers=auth(world.customer)).json()] == ["Please help", "Checking now"]
    assert len(api.get(url, headers=agent).json()) == 3
    note = api.post(url, json={"body": "secret", "is_internal": True}, headers=auth(world.customer))
    assert note.status_code == 403


def test_customer_reply_moves_the_ticket(api: TestClient, db_session: Session, world: World) -> None:
    ticket = in_team(db_session, world.new_ticket(db_session), world.billing, TicketStatus.WAITING_FOR_CUSTOMER)

    api.post(f"{TICKETS}/{ticket.id}/messages", json={"body": "Here is the receipt"}, headers=auth(world.customer))

    assert api.get(f"{TICKETS}/{ticket.id}", headers=auth(world.customer)).json()["status"] == "IN_PROGRESS"


def test_no_messages_on_closed_tickets(api: TestClient, db_session: Session, world: World) -> None:
    ticket = in_team(db_session, world.new_ticket(db_session), world.billing, TicketStatus.CLOSED)

    response = api.post(f"{TICKETS}/{ticket.id}/messages", json={"body": "hello?"}, headers=auth(world.customer))

    assert response.status_code == 409


# ---------- Status ----------


def test_full_lifecycle_and_history(api: TestClient, db_session: Session, world: World) -> None:
    ticket = in_team(db_session, world.new_ticket(db_session), world.billing)
    url = f"{TICKETS}/{ticket.id}"
    agent = auth(world.billing_agent)

    api.post(f"{url}/status", json={"status": "IN_PROGRESS"}, headers=agent)
    resolved = api.post(f"{url}/status", json={"status": "RESOLVED", "reason": "Refunded"}, headers=agent).json()
    closed = api.post(f"{url}/status", json={"status": "CLOSED"}, headers=auth(world.customer)).json()

    assert resolved["resolved_at"] is not None
    assert closed["status"] == "CLOSED"
    history = api.get(f"{url}/history", headers=agent).json()
    assert [(h["to_status"], h["changed_by"]["full_name"]) for h in history] == [
        ("OPEN", "Casey Customer"),
        ("IN_PROGRESS", "Bill Agent"),
        ("RESOLVED", "Bill Agent"),
        ("CLOSED", "Casey Customer"),
    ]
    assert api.get(f"{url}/history", headers=auth(world.customer)).status_code == 403


def test_bad_status_moves(api: TestClient, db_session: Session, world: World) -> None:
    ticket = world.new_ticket(db_session)
    url = f"{TICKETS}/{ticket.id}/status"

    assert api.post(url, json={"status": "RESOLVED"}, headers=auth(world.customer)).status_code == 403
    assert api.post(url, json={"status": "ESCALATED"}, headers=auth(world.manager)).status_code == 409
    assert api.post(url, json={"status": "DONE"}, headers=auth(world.manager)).status_code == 422


# ---------- Assignment ----------


def test_manager_assigns_to_team_and_agent(api: TestClient, db_session: Session, world: World) -> None:
    ticket = world.new_ticket(db_session)
    url = f"{TICKETS}/{ticket.id}/assign"

    to_team = api.post(url, json={"team_id": str(world.billing.id)}, headers=auth(world.manager)).json()
    to_agent = api.post(url, json={"assignee_id": str(world.billing_agent.id)}, headers=auth(world.manager)).json()

    assert to_team["team"]["name"] == "Billing Team" and to_team["assignee"] is None
    assert to_agent["assignee"]["full_name"] == "Bill Agent"


def test_assignment_rules(api: TestClient, db_session: Session, world: World) -> None:
    ticket = in_team(db_session, world.new_ticket(db_session), world.billing)
    url = f"{TICKETS}/{ticket.id}/assign"

    # Tess isn't in the Billing team.
    assert api.post(url, json={"assignee_id": str(world.tech_agent.id)}, headers=auth(world.manager)).status_code == 400
    # An agent can take a ticket for themselves...
    assert (
        api.post(url, json={"assignee_id": str(world.billing_agent.id)}, headers=auth(world.billing_agent)).status_code
        == 200
    )
    # ...but can't hand it to someone else or move it to another team.
    assert (
        api.post(url, json={"assignee_id": str(world.manager.id)}, headers=auth(world.billing_agent)).status_code == 403
    )
    assert api.post(url, json={"team_id": str(world.tech.id)}, headers=auth(world.billing_agent)).status_code == 403
    assert api.post(url, json={"team_id": str(world.tech.id)}, headers=auth(world.customer)).status_code == 403


# ---------- Escalation ----------


def test_escalate_and_deescalate(api: TestClient, db_session: Session, world: World) -> None:
    ticket = in_team(db_session, world.new_ticket(db_session), world.billing, TicketStatus.IN_PROGRESS)
    url = f"{TICKETS}/{ticket.id}"

    escalated = api.post(f"{url}/escalate", json={"reason": "Chargeback threat"}, headers=auth(world.billing_agent))
    assert escalated.json()["status"] == "ESCALATED"
    assert api.post(f"{url}/escalate", json={"reason": "again"}, headers=auth(world.billing_agent)).status_code == 409

    assert (
        api.post(f"{url}/status", json={"status": "IN_PROGRESS"}, headers=auth(world.billing_agent)).status_code == 403
    )
    assert api.post(f"{url}/status", json={"status": "IN_PROGRESS"}, headers=auth(world.manager)).status_code == 200

    escalation = db_session.execute(select(TicketEscalation)).scalar_one()
    db_session.refresh(escalation)
    assert escalation.reason == "Chargeback threat"
    assert escalation.resolved_by_id == world.manager.id


def test_customers_cannot_escalate(api: TestClient, db_session: Session, world: World) -> None:
    ticket = world.new_ticket(db_session)

    response = api.post(f"{TICKETS}/{ticket.id}/escalate", json={"reason": "please"}, headers=auth(world.customer))

    assert response.status_code == 403
