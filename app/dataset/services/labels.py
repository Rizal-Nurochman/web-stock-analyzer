"""Impor label manual dan keputusan review dari CSV hasil anotasi.

Kolom yang dibaca: article_id, stock_code, dan salah satu/lebih dari
manual_sentiment (positive|negative|neutral|kosong), review_status
(unreviewed|reviewed|rejected), relevance (relevant|review|irrelevant), reviewer_note.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select

from app.dataset.database.session import Database
from app.dataset.models.schema import Article, ArticleStock
from app.dataset.services.sentiment import LABELS

REVIEW_STATUSES = ("unreviewed", "reviewed", "rejected")
RELEVANCE = ("relevant", "review", "irrelevant")


@dataclass
class ImportReport:
    updated: int = 0
    errors: list[str] = field(default_factory=list)


def import_labels(db: Database, path: Path) -> ImportReport:
    report = ImportReport()
    with open(path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    with db.write() as s:
        touched_articles = set()
        for line, row in enumerate(rows, start=2):
            pair = s.scalars(select(ArticleStock).where(
                ArticleStock.article_id == (row.get("article_id") or "").strip(),
                ArticleStock.stock_code == (row.get("stock_code") or "").strip().upper(),
            )).first()
            if pair is None:
                report.errors.append(f"Baris {line}: pasangan artikel-emiten tidak ditemukan")
                continue
            sentiment = (row.get("manual_sentiment") or "").strip().lower()
            if sentiment and sentiment not in LABELS:
                report.errors.append(f"Baris {line}: manual_sentiment tidak valid: {sentiment}")
                continue
            review = (row.get("review_status") or "").strip().lower()
            if review and review not in REVIEW_STATUSES:
                report.errors.append(f"Baris {line}: review_status tidak valid: {review}")
                continue
            relevance = (row.get("relevance") or "").strip().lower()
            if relevance and relevance not in RELEVANCE:
                report.errors.append(f"Baris {line}: relevance tidak valid: {relevance}")
                continue
            if "manual_sentiment" in row:
                pair.manual_sentiment = sentiment or None
            if review:
                pair.review_status = review
            if relevance == "irrelevant":
                pair.relevance, pair.review_status = "review", "rejected"
            elif relevance:
                pair.relevance = relevance
            if row.get("reviewer_note"):
                pair.reviewer_note = row["reviewer_note"].strip()
            touched_articles.add(pair.article_id)
            report.updated += 1
        s.flush()
        # Status artikel mengikuti relasinya: relevan jika ada emiten relevan yang tidak ditolak.
        for article_id in touched_articles:
            article = s.get(Article, article_id)
            pairs = list(s.scalars(select(ArticleStock).where(ArticleStock.article_id == article_id)))
            relevant = any(p.relevance == "relevant" and p.review_status != "rejected" for p in pairs)
            article.relevance_status = "relevant" if relevant else "review"
    return report
