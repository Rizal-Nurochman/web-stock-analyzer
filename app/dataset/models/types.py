"""Struktur data yang mengalir di pipeline sebelum disimpan."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True)
class Candidate:
    """URL artikel hasil penemuan (indeks, sitemap, tag, RSS)."""

    url: str
    title: str | None = None
    published_hint: date | None = None
    discovered_via: str = ""
    category: str | None = None
    # False untuk sumber yang sudah tertarget (halaman tag ticker): tidak perlu prafilter judul.
    prefilter: bool = True


@dataclass
class ExtractedArticle:
    url: str
    canonical_url: str
    title: str
    content: str
    author: str | None
    published_at: datetime | None  # zona Asia/Jakarta
    category: str | None
    language: str
    paywalled: bool = False


@dataclass
class StockMatch:
    code: str
    name: str
    relevance: str  # relevant | review
    score: float
    mention_count: int
    in_title: bool
    matched_terms: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
