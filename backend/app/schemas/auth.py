from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field

from app.schemas.user import UserOut

# Lowercase + trimmed, so "Ana@Example.com " and "ana@example.com" are the same account.
Email = Annotated[EmailStr, AfterValidator(lambda value: value.strip().lower())]


class RegisterRequest(BaseModel):
    # extra="forbid": a client can't sneak in fields like "role": "ADMIN".
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: Email
    # Max length stops someone sending a huge "password" to waste CPU on hashing.
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Email
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    """Returned by login and refresh. The refresh token is NOT here: it's in an httpOnly cookie."""

    access_token: str
    token_type: str = "bearer"  # noqa: S105 (the OAuth2 token type name, not a password)
    expires_in: int  # seconds
    user: UserOut
