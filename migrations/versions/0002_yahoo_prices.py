"""Sumber harga per baris dan status sinkronisasi Yahoo Finance

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("prices") as batch:
        batch.add_column(sa.Column("source", sa.String(16), nullable=False, server_default="csv"))
    op.create_table(
        "price_sync_status",
        sa.Column("ticker", sa.String(8), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_session_date", sa.Date(), nullable=True),
        sa.Column("rows", sa.Integer(), nullable=True),
        sa.Column("new_rows", sa.Integer(), nullable=True),
        sa.Column("skipped_holidays", sa.Integer(), nullable=True),
        sa.Column("corrected_rows", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("price_sync_status")
    with op.batch_alter_table("prices") as batch:
        batch.drop_column("source")
