"""Register, login, refresh, logout and /me through the API."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_refresh_token
from app.models import RefreshToken, User
from tests.helpers import PASSWORD, login, make_user

pytestmark = pytest.mark.db

AUTH = "/api/v1/auth"


def test_register_creates_a_customer(api: TestClient, db_session: Session) -> None:
    response = api.post(
        f"{AUTH}/register", json={"email": " Ana@Example.COM ", "password": PASSWORD, "full_name": "Ana"}
    )

    assert response.status_code == 201
    assert response.json()["email"] == "ana@example.com"
    assert response.json()["role"] == "CUSTOMER"
    assert "password" not in response.text
    stored = db_session.execute(select(User)).scalar_one()
    assert stored.password_hash.startswith("$argon2id$")


def test_register_same_email_twice_is_409(api: TestClient) -> None:
    body = {"email": "ana@example.com", "password": PASSWORD, "full_name": "Ana"}
    api.post(f"{AUTH}/register", json=body)

    assert api.post(f"{AUTH}/register", json=body | {"email": "ANA@example.com"}).status_code == 409


@pytest.mark.parametrize(
    "change",
    [
        {"role": "ADMIN"},  # can't choose your own role
        {"password": "short"},
        {"email": "not-an-email"},
        {"full_name": ""},
    ],
)
def test_register_rejects_bad_input(api: TestClient, change: dict) -> None:
    body = {"email": "ana@example.com", "password": PASSWORD, "full_name": "Ana"} | change

    assert api.post(f"{AUTH}/register", json=body).status_code == 422


def test_login_returns_token_and_safe_cookie(api: TestClient, db_session: Session) -> None:
    make_user(db_session, "ana@example.com")

    response = api.post(f"{AUTH}/login", json={"email": "ana@example.com", "password": PASSWORD})

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert "refresh_token" not in response.json()  # only in the cookie
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/api/v1/auth" in cookie


@pytest.mark.parametrize("email, password", [("ana@example.com", "wrong-password"), ("nobody@example.com", PASSWORD)])
def test_login_failures_all_look_the_same(api: TestClient, db_session: Session, email: str, password: str) -> None:
    make_user(db_session, "ana@example.com")

    response = api.post(f"{AUTH}/login", json={"email": email, "password": password})

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password"}


def test_disabled_user_cannot_log_in(api: TestClient, db_session: Session) -> None:
    user = make_user(db_session, "ana@example.com")
    user.is_active = False
    db_session.commit()

    assert api.post(f"{AUTH}/login", json={"email": "ana@example.com", "password": PASSWORD}).status_code == 401


def test_me(api: TestClient, db_session: Session) -> None:
    make_user(db_session, "ana@example.com")
    headers = login(api, "ana@example.com")

    assert api.get(f"{AUTH}/me", headers=headers).json()["email"] == "ana@example.com"


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer nonsense"}])
def test_me_needs_a_valid_token(api: TestClient, headers: dict) -> None:
    assert api.get(f"{AUTH}/me", headers=headers).status_code == 401


def test_me_rejects_expired_token(api: TestClient, db_session: Session) -> None:
    user = make_user(db_session, "ana@example.com")
    token, _ = create_access_token(user.id, expires_in=timedelta(seconds=-1))

    assert api.get(f"{AUTH}/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_token_stops_working_when_user_is_disabled(api: TestClient, db_session: Session) -> None:
    user = make_user(db_session, "ana@example.com")
    headers = login(api, "ana@example.com")
    user.is_active = False
    db_session.commit()

    assert api.get(f"{AUTH}/me", headers=headers).status_code == 401


def test_refresh_gives_new_tokens_and_old_refresh_token_stops_working(api: TestClient, db_session: Session) -> None:
    make_user(db_session, "ana@example.com")
    login(api, "ana@example.com")
    old_cookie = api.cookies.get("refresh_token")

    response = api.post(f"{AUTH}/refresh")

    assert response.status_code == 200
    assert api.cookies.get("refresh_token") != old_cookie
    # The old refresh token was deleted, so it can't be used again.
    api.cookies.clear()
    api.cookies.set("refresh_token", old_cookie)
    assert api.post(f"{AUTH}/refresh").status_code == 401


def test_only_the_hash_of_the_refresh_token_is_stored(api: TestClient, db_session: Session) -> None:
    make_user(db_session, "ana@example.com")
    login(api, "ana@example.com")
    plain = api.cookies.get("refresh_token")

    stored = db_session.execute(select(RefreshToken.token_hash)).scalars().all()

    assert stored == [hash_refresh_token(plain)]


def test_refresh_without_cookie_is_401(api: TestClient) -> None:
    assert api.post(f"{AUTH}/refresh").status_code == 401


def test_logout_ends_the_session(api: TestClient, db_session: Session) -> None:
    make_user(db_session, "ana@example.com")
    login(api, "ana@example.com")
    cookie = api.cookies.get("refresh_token")

    assert api.post(f"{AUTH}/logout").status_code == 204

    api.cookies.set("refresh_token", cookie)
    assert api.post(f"{AUTH}/refresh").status_code == 401
