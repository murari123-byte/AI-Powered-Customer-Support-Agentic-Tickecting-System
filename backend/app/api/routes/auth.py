from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.models import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.user import UserOut
from app.services import auth_service
from app.services.auth_service import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    IssuedTokens,
)

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
COOKIE_PATH = "/api/v1/auth"  # the browser sends the cookie only to auth endpoints


def _set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.refresh_token_expire_days * 24 * 3600,
        path=COOKIE_PATH,
        httponly=True,  # JavaScript can't read it, so an XSS bug can't steal it
        secure=settings.auth_cookie_secure,  # HTTPS only (browsers allow http://localhost)
        samesite="strict",  # not sent on requests started by other websites (CSRF protection)
    )


def _token_response(response: Response, issued: IssuedTokens) -> TokenResponse:
    _set_refresh_cookie(response, issued.refresh_token)
    response.headers["Cache-Control"] = "no-store"
    return TokenResponse(
        access_token=issued.access_token, expires_in=issued.expires_in, user=UserOut.model_validate(issued.user)
    )


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("register", limit=5, window_seconds=3600))],  # 5 accounts per hour per IP
)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> User:
    """Create a CUSTOMER account."""
    try:
        return auth_service.register(db, email=body.email, password=body.password, full_name=body.full_name)
    except EmailAlreadyRegisteredError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email is already registered") from None


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit("login", limit=10, window_seconds=60))],  # 10 tries per minute per IP
)
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        user = auth_service.authenticate(db, email=body.email, password=body.password)
    except InvalidCredentialsError:
        # Same message for unknown email, wrong password and disabled account.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password") from None
    return _token_response(response, auth_service.issue_tokens(db, user))


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    response: Response, refresh_token: str | None = Cookie(default=None), db: Session = Depends(get_db)
) -> TokenResponse:
    """Swap the refresh cookie for a new access token and a new refresh cookie."""
    try:
        if not refresh_token:
            raise InvalidRefreshTokenError()
        return _token_response(response, auth_service.refresh(db, refresh_token))
    except InvalidRefreshTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please log in again") from None


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, refresh_token: str | None = Cookie(default=None), db: Session = Depends(get_db)) -> None:
    """End this session. The access token still works until it expires (max 15 minutes)."""
    auth_service.logout(db, refresh_token)
    response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
