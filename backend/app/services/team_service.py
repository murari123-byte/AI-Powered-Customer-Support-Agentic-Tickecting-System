"""Teams and team membership."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.roles import STAFF
from app.models import Team, TeamMember, User


class TeamNotFoundError(Exception):
    pass


class TeamNameTakenError(Exception):
    pass


class InvalidMemberError(Exception):
    """User can't join a team: unknown, inactive, or not support staff."""


def list_teams(db: Session) -> list[Team]:
    return list(db.execute(select(Team).order_by(Team.name)).scalars())


def get_team(db: Session, team_id: uuid.UUID) -> Team:
    team = db.get(Team, team_id)
    if team is None:
        raise TeamNotFoundError()
    return team


def _check_name_free(db: Session, name: str, except_id: uuid.UUID | None = None) -> None:
    # Case-insensitive, so "Billing" and "billing" can't both exist.
    query = select(Team.id).where(func.lower(Team.name) == name.lower())
    if except_id is not None:
        query = query.where(Team.id != except_id)
    if db.execute(query).first() is not None:
        raise TeamNameTakenError()


def create_team(db: Session, *, name: str, description: str | None) -> Team:
    _check_name_free(db, name)
    team = Team(name=name, description=description)
    db.add(team)
    db.commit()
    db.refresh(team)
    return team


def update_team(db: Session, team_id: uuid.UUID, changes: dict) -> Team:
    team = get_team(db, team_id)
    if "name" in changes:
        _check_name_free(db, changes["name"], except_id=team.id)
    for field, value in changes.items():
        setattr(team, field, value)
    db.commit()
    db.refresh(team)
    return team


def add_member(db: Session, team_id: uuid.UUID, user_id: uuid.UUID, *, is_lead: bool) -> TeamMember:
    """Add a staff user to a team (or update their lead flag if they're already in it)."""
    team = get_team(db, team_id)
    user = db.get(User, user_id)
    if user is None or not user.is_active or user.role not in STAFF:
        raise InvalidMemberError("Only active support staff can join a team")

    member = db.get(TeamMember, (team.id, user.id)) or TeamMember(team_id=team.id, user_id=user.id)
    member.is_lead = is_lead
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def remove_member(db: Session, team_id: uuid.UUID, user_id: uuid.UUID) -> None:
    member = db.get(TeamMember, (team_id, user_id))
    if member is None:
        raise InvalidMemberError("User is not a member of this team")
    db.delete(member)
    db.commit()
