"""hands.status_reason

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-17
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("hands") as batch:
        batch.add_column(sa.Column("status_reason", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("hands") as batch:
        batch.drop_column("status_reason")
