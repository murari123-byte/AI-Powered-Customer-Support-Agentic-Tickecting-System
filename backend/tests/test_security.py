"""Password hashing and tokens. Pure unit tests: no database."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)


def test_passwords_are_hashed_with_argon2_and_salted() -> None:
    first, second = hash_password("correct horse"), hash_password("correct horse")

    assert first.startswith("$argon2id$")
    assert first != second  # a new random salt each time
    assert verify_password("correct horse", first)
    assert not verify_password("wrong", first)
    assert not verify_password("correct horse", "not-a-hash")


def test_access_token_round_trip() -> None:
    user_id = uuid.uuid4()
    token, expires_in = create_access_token(user_id)

    assert decode_access_token(token) == user_id
    assert expires_in > 0


def test_token_holds_only_the_user_id_and_times() -> None:
    token, _ = create_access_token(uuid.uuid4())

    assert set(jwt.decode(token, options={"verify_signature": False})) == {"sub", "iat", "exp"}


def test_expired_token_is_rejected() -> None:
    token, _ = create_access_token(uuid.uuid4(), expires_in=timedelta(seconds=-1))

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def _claims() -> dict:
    now = datetime.now(UTC)
    return {"sub": str(uuid.uuid4()), "iat": now, "exp": now + timedelta(minutes=5)}


def test_token_signed_with_another_key_is_rejected() -> None:
    forged = jwt.encode(_claims(), "an-attacker-key-that-is-long-enough-123", algorithm="HS256")

    with pytest.raises(InvalidTokenError):
        decode_access_token(forged)


def test_unsigned_alg_none_token_is_rejected() -> None:
    unsigned = jwt.encode(_claims(), key=None, algorithm="none")

    with pytest.raises(InvalidTokenError):
        decode_access_token(unsigned)


@pytest.mark.parametrize("garbage", ["", "abc", "a.b.c"])
def test_garbage_is_rejected(garbage: str) -> None:
    with pytest.raises(InvalidTokenError):
        decode_access_token(garbage)


def test_refresh_tokens_are_random_and_stored_as_hashes() -> None:
    token = new_refresh_token()

    assert token != new_refresh_token()
    assert len(hash_refresh_token(token)) == 64
    assert hash_refresh_token(token) != token
