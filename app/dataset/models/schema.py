"""Skema SQLite dataset. Artikel dan relasi artikel-emiten disimpan terpisah."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Article(Base):
    __tablename__ = "articles"

    article_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    author: Mapped[str | None] = mapped_column(Text)
    # ISO 8601 dengan offset +07:00 (Asia/Jakarta).
    published_at: Mapped[str | None] = mapped_column(String(32), index=True)
    scraped_at: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str | None] = mapped_column(String(128))
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="id")
    content_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    title_key: Mapped[str] = mapped_column(Text, index=True, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    # relevant: dataset utama. review: relevansi belum pasti, perlu diperiksa manusia.
    relevance_status: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    duplicate_group_id: Mapped[str | None] = mapped_column(String(64), index=True)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    duplicate_reason: Mapped[str | None] = mapped_column(String(32))
    discovered_via: Mapped[str | None] = mapped_column(String(64))

    stocks: Mapped[list["ArticleStock"]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )


class ArticleStock(Base):
    """Satu pasangan artikel-emiten: unit analisis Target-Based Sentiment Analysis."""

    __tablename__ = "article_stocks"
    __table_args__ = (UniqueConstraint("article_id", "stock_code", name="uq_article_stock"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[str] = mapped_column(
        ForeignKey("articles.article_id", ondelete="CASCADE"), index=True, nullable=False
    )
    stock_code: Mapped[str] = mapped_column(String(8), index=True, nullable=False)
    stock_name: Mapped[str] = mapped_column(Text, nullable=False)
    relevance: Mapped[str] = mapped_column(String(16), nullable=False)  # relevant | review
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False)
    mention_count: Mapped[int] = mapped_column(Integer, nullable=False)
    in_title: Mapped[bool] = mapped_column(Boolean, nullable=False)
    matched_terms: Mapped[str] = mapped_column(Text, nullable=False)
    relevance_reasons: Mapped[str] = mapped_column(Text, nullable=False)
    # Diisi hanya oleh model yang dikonfigurasi. Kosong berarti belum diprediksi.
    predicted_sentiment: Mapped[str | None] = mapped_column(String(16))
    sentiment_confidence: Mapped[float | None] = mapped_column(Float)
    sentiment_model: Mapped[str | None] = mapped_column(String(128))
    # Label manusia (ground truth). Terpisah dari prediksi.
    manual_sentiment: Mapped[str | None] = mapped_column(String(16))
    review_status: Mapped[str] = mapped_column(String(16), nullable=False, default="unreviewed")
    reviewer_note: Mapped[str | None] = mapped_column(Text)

    article: Mapped[Article] = relationship(back_populates="stocks")


class SeenUrl(Base):
    """Setiap URL yang sudah diproses, termasuk yang ditolak. Dasar resume dan anti-ulang."""

    __tablename__ = "seen_urls"

    canonical_url: Mapped[str] = mapped_column(String(1024), primary_key=True)
    source: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    # saved | irrelevant | out_of_range | no_content | paywalled | not_indonesian |
    # robots_disallowed | failed | blocked
    status: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    checked_at: Mapped[str] = mapped_column(String(32), nullable=False)


class Checkpoint(Base):
    """Unit penemuan yang sudah selesai (mis. satu tanggal indeks atau satu file sitemap)."""

    __tablename__ = "checkpoints"

    source: Mapped[str] = mapped_column(String(64), primary_key=True)
    unit: Mapped[str] = mapped_column(String(256), primary_key=True)
    completed_at: Mapped[str] = mapped_column(String(32), nullable=False)
    candidates: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class SourceStatus(Base):
    __tablename__ = "source_status"

    source: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # available | partial | unavailable
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    access_method: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[str] = mapped_column(String(32), nullable=False)


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[str] = mapped_column(String(32), nullable=False)
    finished_at: Mapped[str | None] = mapped_column(String(32))
    params: Mapped[str] = mapped_column(Text, nullable=False)
    stats: Mapped[str | None] = mapped_column(Text)


def now_wib_iso() -> str:
    from app.config import WIB

    return datetime.now(WIB).replace(microsecond=0).isoformat()
