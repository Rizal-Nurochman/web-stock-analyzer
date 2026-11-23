"""Berita dan sentimen tidak lagi disimpan: hapus tabel berita

Berita kini dipantau live dan dinilai di memori proses (app/news/live.py).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("feed_status")
    op.drop_index("ix_article_tickers_ticker", table_name="article_tickers")
    op.drop_index("ix_article_tickers_article_id", table_name="article_tickers")
    op.drop_table("article_tickers")
    op.drop_index("ix_articles_published_at", table_name="articles")
    op.drop_table("articles")


def downgrade() -> None:
    op.create_table(
        "articles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("canonical_url", sa.String(1024), nullable=False, unique=True),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("publisher", sa.String(64), nullable=False),
        sa.Column("source_feed_id", sa.String(64), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=True),
    )
    op.create_index("ix_articles_published_at", "articles", ["published_at"])
    op.create_table(
        "article_tickers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("article_id", sa.Integer(), sa.ForeignKey("articles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ticker", sa.String(8), nullable=False),
        sa.Column("sentiment", sa.String(16), nullable=True),
        sa.UniqueConstraint("article_id", "ticker", name="uq_article_ticker"),
    )
    op.create_index("ix_article_tickers_article_id", "article_tickers", ["article_id"])
    op.create_index("ix_article_tickers_ticker", "article_tickers", ["ticker"])
    op.create_table(
        "feed_status",
        sa.Column("feed_id", sa.String(64), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_item_count", sa.Integer(), nullable=True),
        sa.Column("last_new_count", sa.Integer(), nullable=True),
    )
