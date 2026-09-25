"""Roles: who can manage users (RBAC)."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.cli import create_admin
from app.core.roles import Role
from tests.helpers import PASSWORD, auth, login, make_user

pytestmark = pytest.mark.db

USERS = "/api/v1/admin/users"


@pytest.mark.parametrize(
    "role, expected",
    [(Role.CUSTOMER, 403), (Role.SUPPORT_AGENT, 403), (Role.SUPPORT_MANAGER, 200), (Role.ADMIN, 200)],
)
def test_who_can_list_users(api: TestClient, db_session: Session, role: Role, expected: int) -> None:
    user = make_user(db_session, "someone@example.com", role)

    assert api.get(USERS, headers=auth(user)).status_code == expected


def test_list_users_needs_login(api: TestClient) -> None:
    assert api.get(USERS).status_code == 401


def test_search_users(api: TestClient, db_session: Session) -> None:
    admin = make_user(db_session, "admin@example.com", Role.ADMIN)
    make_user(db_session, "casey@example.com", name="Casey")

    found = api.get(USERS, params={"search": "CASEY"}, headers=auth(admin)).json()
    wildcard = api.get(USERS, params={"search": "%"}, headers=auth(admin)).json()

    assert [u["email"] for u in found["items"]] == ["casey@example.com"]
    assert wildcard["total"] == 0  # % is treated as a normal character


def test_admin_changes_a_role_and_it_works_immediately(api: TestClient, db_session: Session) -> None:
    admin = make_user(db_session, "admin@example.com", Role.ADMIN)
    user = make_user(db_session, "casey@example.com")
    user_headers = login(api, "casey@example.com")
    assert api.get(USERS, headers=user_headers).status_code == 403

    response = api.patch(f"{USERS}/{user.id}", json={"role": "SUPPORT_MANAGER"}, headers=auth(admin))

    assert response.json()["role"] == "SUPPORT_MANAGER"
    # Same old access token, new role: the role is read from the database, not the token.
    assert api.get(USERS, headers=user_headers).status_code == 200


def test_only_admin_changes_roles(api: TestClient, db_session: Session) -> None:
    manager = make_user(db_session, "boss@example.com", Role.SUPPORT_MANAGER)
    user = make_user(db_session, "casey@example.com")

    assert api.patch(f"{USERS}/{user.id}", json={"role": "ADMIN"}, headers=auth(manager)).status_code == 403


def test_deactivating_logs_the_user_out(api: TestClient, db_session: Session) -> None:
    admin = make_user(db_session, "admin@example.com", Role.ADMIN)
    user = make_user(db_session, "casey@example.com")
    user_headers = login(api, "casey@example.com")  # also puts their refresh cookie in the client

    api.patch(f"{USERS}/{user.id}", json={"is_active": False}, headers=auth(admin))

    assert api.get("/api/v1/auth/me", headers=user_headers).status_code == 401
    assert api.post("/api/v1/auth/refresh").status_code == 401


@pytest.mark.parametrize("body", [{"role": "SUPPORT_AGENT"}, {"is_active": False}])
def test_admin_cannot_lock_themselves_out(api: TestClient, db_session: Session, body: dict) -> None:
    admin = make_user(db_session, "admin@example.com", Role.ADMIN)

    assert api.patch(f"{USERS}/{admin.id}", json=body, headers=auth(admin)).status_code == 400


@pytest.mark.parametrize("body", [{"role": "SUPERUSER"}, {"password_hash": "x"}])
def test_update_rejects_unknown_values(api: TestClient, db_session: Session, body: dict) -> None:
    admin = make_user(db_session, "admin@example.com", Role.ADMIN)
    user = make_user(db_session, "casey@example.com")

    assert api.patch(f"{USERS}/{user.id}", json=body, headers=auth(admin)).status_code == 422


def test_unknown_user_is_404(api: TestClient, db_session: Session) -> None:
    admin = make_user(db_session, "admin@example.com", Role.ADMIN)

    assert api.patch(f"{USERS}/{uuid.uuid4()}", json={"is_active": True}, headers=auth(admin)).status_code == 404


# ---------- create-admin command ----------


def test_cli_creates_admin(db_session: Session) -> None:
    assert create_admin(db_session, email="Boss@Example.com", name="Boss", password=PASSWORD) == 0


def test_cli_refuses_duplicate_and_short_password(db_session: Session) -> None:
    make_user(db_session, "boss@example.com")

    assert create_admin(db_session, email="boss@example.com", name="Boss", password=PASSWORD) == 1
    assert create_admin(db_session, email="new@example.com", name="New", password="short") == 2
