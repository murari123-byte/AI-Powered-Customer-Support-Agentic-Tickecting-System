import uuid

from pydantic import BaseModel, ConfigDict, Field


class UserRef(BaseModel):
    """Short public view of a person: no email, no role."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str


class TeamMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user: UserRef
    is_lead: bool


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    is_active: bool
    members: list[TeamMemberOut]


class TeamCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=1000)


class TeamUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    is_active: bool | None = None


class AddMember(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID
    is_lead: bool = False
