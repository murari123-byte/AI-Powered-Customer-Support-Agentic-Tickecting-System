"""Small helpers shared by the tests."""

from dataclasses import dataclass

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.roles import Role
from app.core.security import create_access_token
from app.models import Team, TeamMember, Ticket, User
from app.services import ticket_service
from app.services.auth_service import create_user

PASSWORD = "a-long-test-password"


def make_user(db: Session, email: str, role: Role = Role.CUSTOMER, name: str = "Test User") -> User:
    return create_user(db, email=email, password=PASSWORD, full_name=name, role=role)


def auth(user: User) -> dict[str, str]:
    """Authorization header for this user (skips /login, which has its own tests)."""
    return {"Authorization": f"Bearer {create_access_token(user.id)[0]}"}


def login(api: TestClient, email: str, password: str = PASSWORD) -> dict[str, str]:
    """Log in through the API; returns the auth header. The refresh cookie stays in the client."""
    response = api.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@dataclass
class World:
    """A small support company for ticket tests."""

    customer: User
    other_customer: User
    billing_agent: User
    tech_agent: User
    manager: User
    admin: User
    billing: Team
    tech: Team

    def new_ticket(self, db: Session, subject: str = "Charged twice", customer: User | None = None) -> Ticket:
        return ticket_service.create_ticket(
            db, customer or self.customer, subject=subject, description="Please help", category=None
        )


def build_world(db: Session) -> World:
    customer = make_user(db, "cust@example.com", name="Casey Customer")
    other = make_user(db, "other@example.com", name="Olly Other")
    billing_agent = make_user(db, "bill@example.com", Role.SUPPORT_AGENT, "Bill Agent")
    tech_agent = make_user(db, "tech@example.com", Role.SUPPORT_AGENT, "Tess Agent")
    manager = make_user(db, "boss@example.com", Role.SUPPORT_MANAGER, "Maya Manager")
    admin = make_user(db, "admin@example.com", Role.ADMIN, "Ada Admin")

    billing = Team(name="Billing Team")
    tech = Team(name="Technical Support")
    db.add_all([billing, tech])
    db.flush()
    db.add_all(
        [
            TeamMember(team_id=billing.id, user_id=billing_agent.id),
            TeamMember(team_id=billing.id, user_id=manager.id, is_lead=True),
            TeamMember(team_id=tech.id, user_id=tech_agent.id),
        ]
    )
    db.commit()
    return World(customer, other, billing_agent, tech_agent, manager, admin, billing, tech)
