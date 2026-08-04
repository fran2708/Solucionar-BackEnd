"""Add GRUPO/ACCION security model (groups, actions, user_groups, group_actions)
and PERSONA/USUARIO fields on users.

Revision ID: g1_add_security_model
Revises: f1_rename_payment_columns
Create Date: 2026-08-03
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "g1_add_security_model"
down_revision = "f1_rename_payment_columns"
branch_labels = None
depends_on = None


# Acciones que reemplazan los checks de rol existentes en el código.
ACTIONS = [
    ("categorias", "crear", "Crear una nueva categoría de servicios"),
    ("categorias", "eliminar", "Eliminar una categoría de servicios"),
    ("servicios", "crear", "Publicar un nuevo servicio"),
    ("servicios", "administrar", "Listar y administrar los propios servicios"),
    ("servicios", "ver_todos", "Ver todos los servicios de cualquier proveedor"),
    ("servicios", "editar_cualquiera", "Editar/eliminar servicios de cualquier proveedor"),
    ("reservations", "gestionar_como_proveedor", "Aceptar/rechazar/finalizar reservas como proveedor"),
    ("usuarios", "administrar_permisos", "Administrar grupos, acciones y bloqueo de usuarios"),
]

# Grupos y las acciones que otorgan (mismos nombres que Role para backfill directo).
GROUPS = {
    "ADMIN": [
        ("categorias", "crear"),
        ("categorias", "eliminar"),
        ("servicios", "ver_todos"),
        ("servicios", "editar_cualquiera"),
        ("usuarios", "administrar_permisos"),
    ],
    "PROVIDER": [
        ("servicios", "crear"),
        ("servicios", "administrar"),
        ("reservations", "gestionar_como_proveedor"),
    ],
    "USER": [],
}


def upgrade() -> None:
    op.create_table(
        "groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_groups_name", "groups", ["name"], unique=True)

    op.create_table(
        "actions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("modulo", sa.String(), nullable=False),
        sa.UniqueConstraint("modulo", "name", name="uq_action_modulo_name"),
    )

    op.create_table(
        "group_actions",
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("groups.id"), primary_key=True),
        sa.Column("action_id", sa.Integer(), sa.ForeignKey("actions.id"), primary_key=True),
    )

    op.create_table(
        "user_groups",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("groups.id"), primary_key=True),
    )

    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("tipo_documento", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("nro_documento", sa.String(), nullable=True))
        batch.add_column(sa.Column("fecha_nacimiento", sa.Date(), nullable=True))
        batch.add_column(sa.Column("ultimo_acceso", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("motivo_bloqueo", sa.String(), nullable=True))

    conn = op.get_bind()
    metadata = sa.MetaData()
    groups_t = sa.Table("groups", metadata, autoload_with=conn)
    actions_t = sa.Table("actions", metadata, autoload_with=conn)
    group_actions_t = sa.Table("group_actions", metadata, autoload_with=conn)
    user_groups_t = sa.Table("user_groups", metadata, autoload_with=conn)
    users_t = sa.Table("users", metadata, autoload_with=conn)

    # Seed de acciones
    action_ids: dict[tuple[str, str], int] = {}
    for modulo, name, description in ACTIONS:
        result = conn.execute(
            actions_t.insert().values(modulo=modulo, name=name, description=description)
        )
        action_ids[(modulo, name)] = result.inserted_primary_key[0]

    # Seed de grupos + relación con acciones
    group_ids: dict[str, int] = {}
    for group_name, group_actions in GROUPS.items():
        result = conn.execute(groups_t.insert().values(name=group_name, active=True))
        group_id = result.inserted_primary_key[0]
        group_ids[group_name] = group_id
        for modulo, name in group_actions:
            conn.execute(
                group_actions_t.insert().values(
                    group_id=group_id, action_id=action_ids[(modulo, name)]
                )
            )

    # Backfill: cada usuario existente entra al grupo homónimo a su role actual.
    existing_users = conn.execute(sa.select(users_t.c.id, users_t.c.role)).fetchall()
    for user_id, role in existing_users:
        group_id = group_ids.get(role)
        if group_id is not None:
            conn.execute(user_groups_t.insert().values(user_id=user_id, group_id=group_id))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("motivo_bloqueo")
        batch.drop_column("ultimo_acceso")
        batch.drop_column("fecha_nacimiento")
        batch.drop_column("nro_documento")
        batch.drop_column("tipo_documento")

    op.drop_table("user_groups")
    op.drop_table("group_actions")
    op.drop_table("actions")
    op.drop_index("ix_groups_name", table_name="groups")
    op.drop_table("groups")
