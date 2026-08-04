from __future__ import annotations
from typing import Optional, TYPE_CHECKING, List, Annotated
from datetime import datetime, date
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy.orm import relationship
from sqlalchemy import Column
from sqlalchemy import Enum as SQLEnum
from core.enums import Role, TipoDocumento

from . import groups as _groups  # noqa: F401  (registra Group/Action/UserGroup/GroupAction en el metadata)

if TYPE_CHECKING:
    from .services import Service
    from .reservations import Reservation
    from .payments import Payment
    from .groups import Group

class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    full_name: str
    email: str = Field(index=True, unique=True)
    password_hash: str
    phone: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    is_active: bool = Field(default=True)
    # Store role as a string at the pydantic level but use a SQLAlchemy
    # Enum column so the DB keeps enum values. Using `str` here avoids
    # SQLModel trying to inspect a forward-ref/string annotation.
    role: str = Field(default=Role.USER.value, sa_column=Column(SQLEnum(Role, name="role_enum")))
    created_at: datetime | None = Field(default_factory=datetime.utcnow)

    # Campos de PERSONA/USUARIO (modelo de seguridad del diagrama de clases)
    tipo_documento: Optional[TipoDocumento] = None
    nro_documento: Optional[str] = None
    fecha_nacimiento: Optional[date] = None
    ultimo_acceso: Optional[datetime] = None
    motivo_bloqueo: Optional[str] = None

    # Nota: relación inversa con ProviderProfile se gestiona desde ProviderProfile.user_id

    # Relationships
    services_provided: Annotated[List["Service"], Relationship(back_populates="provider")] = Relationship(
        back_populates="provider",
        sa_relationship=relationship("Service", back_populates="provider"),
    )
    reservations: Annotated[List["Reservation"], Relationship(back_populates="client")] = Relationship(
        back_populates="client",
        sa_relationship=relationship("Reservation", back_populates="client"),
    )
    payments: Annotated[List["Payment"], Relationship(back_populates="payer")] = Relationship(
        back_populates="payer",
        sa_relationship=relationship("Payment", back_populates="payer"),
    )
    groups: List["Group"] = Relationship(
        sa_relationship=relationship("Group", secondary="user_groups", uselist=True),
    )
