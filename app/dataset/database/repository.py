"""Operasi baca/tulis yang dipakai pipeline."""

from __future__ import annotations

import json

from sqlalchemy import select

from app.dataset.database.session import Database
from app.dataset.models.schema import (
    Article,
    ArticleStock,
    Checkpoint,
    Run,
    SeenUrl,
    SourceStatus,
    now_wib_iso,
)

# Status yang tidak perlu dicoba ulang saat resume.
TERMINAL_STATUSES = {
    "saved", "irrelevant", "out_of_range", "no_content", "paywalled",
    "not_indonesian", "robots_disallowed",
}
MAX_ATTEMPTS = 3


class Repository:
    def __init__(self, db: Database):
        self.db = db

    # ---------- URL yang sudah diproses ----------
    def should_skip(self, canonical: str) -> bool:
        with self.db.read() as s:
            row = s.get(SeenUrl, canonical)
            if row is None:
                return False
            return row.status in TERMINAL_STATUSES or row.attempts >= MAX_ATTEMPTS

    def mark_seen(self, canonical: str, source: str, url: str, status: str,
                  reason: str | None = None, title: str | None = None) -> None:
        with self.db.write() as s:
            row = s.get(SeenUrl, canonical)
            if row is None:
                s.add(SeenUrl(canonical_url=canonical, source=source, url=url, status=status,
                              reason=reason, title=title, attempts=1, checked_at=now_wib_iso()))
            else:
                row.status, row.reason, row.checked_at = status, reason, now_wib_iso()
                row.title = title or row.title
                row.attempts += 1

    # ---------- Checkpoint penemuan ----------
    def checkpoint_done(self, source: str, unit: str) -> bool:
        with self.db.read() as s:
            return s.get(Checkpoint, (source, unit)) is not None

    def complete_checkpoint(self, source: str, unit: str, candidates: int) -> None:
        with self.db.write() as s:
            s.merge(Checkpoint(source=source, unit=unit, completed_at=now_wib_iso(),
                               candidates=candidates))

    # ---------- Artikel ----------
    def save_article(self, article: Article, stocks: list[ArticleStock]) -> None:
        with self.db.write() as s:
            s.add(article)
            s.flush()
            for stock in stocks:
                stock.article_id = article.article_id
                s.add(stock)

    def articles_near(self, published_from: str, published_to: str) -> list[Article]:
        with self.db.read() as s:
            return list(s.scalars(
                select(Article).where(Article.published_at >= published_from,
                                      Article.published_at <= published_to)
            ))

    def find_by_hash(self, content_hash: str) -> Article | None:
        with self.db.read() as s:
            return s.scalars(select(Article).where(Article.content_hash == content_hash)).first()

    def set_group(self, article_id: str, group_id: str) -> None:
        with self.db.write() as s:
            row = s.get(Article, article_id)
            if row is not None and row.duplicate_group_id is None:
                row.duplicate_group_id = group_id

    # ---------- Status sumber dan run ----------
    def set_source_status(self, source: str, name: str, status: str, method: str, note: str | None) -> None:
        with self.db.write() as s:
            s.merge(SourceStatus(source=source, name=name, status=status, access_method=method,
                                 note=note, checked_at=now_wib_iso()))

    def start_run(self, params: dict) -> int:
        with self.db.write() as s:
            run = Run(started_at=now_wib_iso(), params=json.dumps(params, default=str))
            s.add(run)
            s.flush()
            return run.id

    def finish_run(self, run_id: int, stats: dict) -> None:
        with self.db.write() as s:
            run = s.get(Run, run_id)
            run.finished_at = now_wib_iso()
            run.stats = json.dumps(stats, default=str)
