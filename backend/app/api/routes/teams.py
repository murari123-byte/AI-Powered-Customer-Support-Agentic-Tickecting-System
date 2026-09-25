import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.roles import STAFF, Role
from app.db.session import get_db
from app.models import Team, User
from app.schemas.team import AddMember, TeamCreate, TeamOut, TeamUpdate
from app.services import team_service

router = APIRouter(prefix="/teams", tags=["teams"])

staff_only = require_roles(*STAFF)
admin_only = require_roles(Role.ADMIN)


@router.get("", response_model=list[TeamOut])
def list_teams(_: User = Depends(staff_only), db: Session = Depends(get_db)) -> list[Team]:
    return team_service.list_teams(db)


@router.post("", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
def create_team(body: TeamCreate, _: User = Depends(admin_only), db: Session = Depends(get_db)) -> Team:
    return team_service.create_team(db, name=body.name, description=body.description)


@router.patch("/{team_id}", response_model=TeamOut)
def update_team(
    team_id: uuid.UUID, body: TeamUpdate, _: User = Depends(admin_only), db: Session = Depends(get_db)
) -> Team:
    return team_service.update_team(db, team_id, body.model_dump(exclude_unset=True))


@router.post("/{team_id}/members", response_model=TeamOut)
def add_member(
    team_id: uuid.UUID, body: AddMember, _: User = Depends(admin_only), db: Session = Depends(get_db)
) -> Team:
    team_service.add_member(db, team_id, body.user_id, is_lead=body.is_lead)
    return team_service.get_team(db, team_id)


@router.delete("/{team_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    team_id: uuid.UUID, user_id: uuid.UUID, _: User = Depends(admin_only), db: Session = Depends(get_db)
) -> None:
    team_service.remove_member(db, team_id, user_id)
