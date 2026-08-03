"""Rename Spanish-named payment columns to English.

Revision ID: f1_rename_payment_columns
Revises: e3_add_txn_status
Create Date: 2026-03-02

Breaking change: the JSON keys returned by all /payments endpoints change.
Frontend must be updated to use the new English field names.

Column mapping:
  estado       -> status
  monto        -> amount
  moneda       -> currency
  comision     -> commission
  neto         -> net_amount
  creado_en    -> created_at
  actualizado_en -> updated_at
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f1_rename_payment_columns"
down_revision = "e3_add_txn_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Rename all Spanish column names in the payments table to English."""
    with op.batch_alter_table("payments") as batch_op:
        batch_op.alter_column("estado", new_column_name="status")
        batch_op.alter_column("monto", new_column_name="amount")
        batch_op.alter_column("moneda", new_column_name="currency")
        batch_op.alter_column("comision", new_column_name="commission")
        batch_op.alter_column("neto", new_column_name="net_amount")
        batch_op.alter_column("creado_en", new_column_name="created_at")
        batch_op.alter_column("actualizado_en", new_column_name="updated_at")

    # Recreate the index on the renamed status column.
    op.create_index("ix_payments_status", "payments", ["status"], unique=False)


def downgrade() -> None:
    """Revert English column names back to the original Spanish names."""
    op.drop_index("ix_payments_status", table_name="payments")

    with op.batch_alter_table("payments") as batch_op:
        batch_op.alter_column("status", new_column_name="estado")
        batch_op.alter_column("amount", new_column_name="monto")
        batch_op.alter_column("currency", new_column_name="moneda")
        batch_op.alter_column("commission", new_column_name="comision")
        batch_op.alter_column("net_amount", new_column_name="neto")
        batch_op.alter_column("created_at", new_column_name="creado_en")
        batch_op.alter_column("updated_at", new_column_name="actualizado_en")
