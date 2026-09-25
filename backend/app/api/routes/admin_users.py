import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.roles import MANAGERS, Role
from app.db.session import get_db
from app.models import User
from app.schemas.user import UserListOut, UserOut, UserUpdate
from app.services import user_service
from app.services.user_service import SelfLockoutError, UserNotFoundError

router = APIRouter(prefix="/admin/users", tags=["admin: users"])


@router.get("", response_model=UserListOut)
def list_users(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, min_length=1, max_length=100),
    _: User = Depends(require_roles(*MANAGERS)),
    db: Session = Depends(get_db),
) -> UserListOut:
    users, total = user_service.list_users(db, limit=limit, offset=offset, search=search)
    return UserListOut(items=[UserOut.model_validate(u) for u in users], total=total)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    admin: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
) -> User:
    """Change a user's role and/or activate/deactivate them (deactivating logs them out)."""
    try:
        return user_service.update_user(db, actor=admin, user_id=user_id, role=body.role, is_active=body.is_active)
    except UserNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found") from None
    except SelfLockoutError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
