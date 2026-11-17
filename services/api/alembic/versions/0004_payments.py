"""payments table (Stripe TEST mode)

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-17
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("chat_id", sa.String(length=32), sa.ForeignKey("chats.id"), nullable=False),
        sa.Column("render_version", sa.Integer(), nullable=False),
        sa.Column("stripe_session_id", sa.String(length=255), nullable=False, unique=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("amount_thb", sa.Integer(), nullable=False),
        sa.Column("pages", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_payments_user_id", "payments", ["user_id"])
    op.create_index("ix_payments_chat_id", "payments", ["chat_id"])


def downgrade() -> None:
    op.drop_index("ix_payments_chat_id", table_name="payments")
    op.drop_index("ix_payments_user_id", table_name="payments")
    op.drop_table("payments")
