from __future__ import annotations

from typing import Annotated, List
from sqlmodel import SQLModel, Field, Relationship, UniqueConstraint
from sqlalchemy.orm import relationship


class GroupAction(SQLModel, table=True):
    __tablename__ = "group_actions"

    group_id: int = Field(foreign_key="groups.id", primary_key=True)
    action_id: int = Field(foreign_key="actions.id", primary_key=True)


class UserGroup(SQLModel, table=True):
    __tablename__ = "user_groups"

    user_id: int = Field(foreign_key="users.id", primary_key=True)
    group_id: int = Field(foreign_key="groups.id", primary_key=True)


class Action(SQLModel, table=True):
    __tablename__ = "actions"
    __table_args__ = (UniqueConstraint("modulo", "name", name="uq_action_modulo_name"),)

    id: int | None = Field(default=None, primary_key=True)
    name: str
    description: str | None = None
    modulo: str

    @property
    def clave(self) -> str:
        return f"{self.modulo}:{self.name}"


class Group(SQLModel, table=True):
    __tablename__ = "groups"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    description: str | None = None
    active: bool = Field(default=True)

    actions: List[Action] = Relationship(
        sa_relationship=relationship("Action", secondary="group_actions", uselist=True),
    )


# --- API Schemas ---

class ActionPublic(SQLModel):
    id: int
    name: str
    description: str | None = None
    modulo: str


class GroupPublic(SQLModel):
    id: int
    name: str
    description: str | None = None
    active: bool
    actions: List[ActionPublic] = []


class GroupCreate(SQLModel):
    name: str
    description: str | None = None


class ActionCreate(SQLModel):
    name: str
    description: str | None = None
    modulo: str
