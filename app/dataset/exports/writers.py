"""Ekspor dataset ke CSV, JSONL, dan salinan SQLite.

File yang dihasilkan di exports_dir:
- banking_news_dataset.csv / .jsonl        artikel relevan (dataset utama)
- banking_news_article_stocks.csv / .jsonl pasangan artikel-emiten untuk TBSA
- banking_news_review.csv / .jsonl         artikel yang relevansinya perlu diperiksa
- banking_news_review_pairs.csv            pasangan artikel-emiten yang perlu diperiksa (untuk import-labels)
- banking_news_unprocessed.csv             URL gagal/paywall/tanpa isi (transparansi)
- banking_news_dataset.sqlite              salinan database
"""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from sqlalchemy import select

from app.dataset.database.session import Database
from app.dataset.models.schema import Article, ArticleStock, SeenUrl

ARTICLE_FIELDS = (
    "article_id", "title", "content", "source", "url", "author", "published_at", "scraped_at",
    "stock_codes", "stock_names", "category", "language", "content_hash",
    "relevance_status", "duplicate_group_id", "is_duplicate", "duplicate_reason", "word_count",
)
PAIR_FIELDS = (
    "article_id", "stock_code", "stock_name", "relevance", "relevance_score", "mention_count",
    "in_title", "matched_terms", "relevance_reasons", "predicted_sentiment",
    "sentiment_confidence", "sentiment_model", "manual_sentiment", "review_status",
    "reviewer_note", "title", "source", "published_at", "url",
)
REVIEW_FIELDS = ARTICLE_FIELDS + ("candidate_stocks", "review_reasons")
UNPROCESSED = ("no_content", "paywalled", "failed", "blocked", "robots_disallowed")


def _article_record(article: Article, pairs: list[ArticleStock], relevant_only: bool) -> dict:
    chosen = [p for p in pairs if p.review_status != "rejected" and (p.relevance == "relevant" or not relevant_only)]
    return {
        "article_id": article.article_id,
        "title": article.title,
        "content": article.content,
        "source": article.source,
        "url": article.url,
        "author": article.author,
        "published_at": article.published_at,
        "scraped_at": article.scraped_at,
        "stock_codes": [p.stock_code for p in chosen],
        "stock_names": [p.stock_name for p in chosen],
        "category": article.category,
        "language": article.language,
        "content_hash": article.content_hash,
        "relevance_status": article.relevance_status,
        "duplicate_group_id": article.duplicate_group_id,
        "is_duplicate": article.is_duplicate,
        "duplicate_reason": article.duplicate_reason,
        "word_count": article.word_count,
    }


def _write_csv(path: Path, fields: tuple[str, ...], records: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            row = {k: ("; ".join(v) if isinstance(v, list) else v) for k, v in record.items()}
            writer.writerow(row)


def _write_jsonl(path: Path, records: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def export_all(db: Database, out_dir: Path, formats: tuple[str, ...] = ("csv", "jsonl", "sqlite")) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    with db.read() as s:
        articles = list(s.scalars(select(Article).order_by(Article.published_at)))
        pairs_by_article: dict[str, list[ArticleStock]] = {}
        for pair in s.scalars(select(ArticleStock)):
            pairs_by_article.setdefault(pair.article_id, []).append(pair)
        unprocessed = list(s.scalars(select(SeenUrl).where(SeenUrl.status.in_(UNPROCESSED))))

    main, review, pair_records, review_pairs = [], [], [], []
    for article in articles:
        pairs = pairs_by_article.get(article.article_id, [])
        if article.relevance_status == "relevant":
            main.append(_article_record(article, pairs, relevant_only=True))
            for p in pairs:
                record = {
                    **{f: getattr(p, f) for f in PAIR_FIELDS if hasattr(p, f)},
                    "title": article.title, "source": article.source,
                    "published_at": article.published_at, "url": article.url,
                }
                if p.relevance == "relevant" and p.review_status != "rejected":
                    pair_records.append(record)
                elif p.review_status != "rejected":
                    review_pairs.append(record)
        else:
            record = _article_record(article, pairs, relevant_only=False)
            record["candidate_stocks"] = [p.stock_code for p in pairs]
            record["review_reasons"] = [f"{p.stock_code}: {p.relevance_reasons}" for p in pairs]
            review.append(record)
            review_pairs.extend(
                {**{f: getattr(p, f) for f in PAIR_FIELDS if hasattr(p, f)}, "title": article.title,
                 "source": article.source, "published_at": article.published_at, "url": article.url}
                for p in pairs if p.review_status != "rejected")

    files = {}
    if "csv" in formats:
        _write_csv(out_dir / "banking_news_dataset.csv", ARTICLE_FIELDS, main)
        _write_csv(out_dir / "banking_news_article_stocks.csv", PAIR_FIELDS, pair_records)
        _write_csv(out_dir / "banking_news_review.csv", REVIEW_FIELDS, review)
        # Satu baris per pasangan yang perlu diperiksa; isi kolom relevance lalu import-labels.
        _write_csv(out_dir / "banking_news_review_pairs.csv", PAIR_FIELDS, review_pairs)
        _write_csv(out_dir / "banking_news_unprocessed.csv",
                   ("source", "status", "reason", "url", "title", "checked_at"),
                   [{"source": u.source, "status": u.status, "reason": u.reason, "url": u.url,
                     "title": u.title, "checked_at": u.checked_at} for u in unprocessed])
        files["csv"] = ["banking_news_dataset.csv", "banking_news_article_stocks.csv",
                        "banking_news_review.csv", "banking_news_review_pairs.csv",
                        "banking_news_unprocessed.csv"]
    if "jsonl" in formats:
        _write_jsonl(out_dir / "banking_news_dataset.jsonl", main)
        _write_jsonl(out_dir / "banking_news_article_stocks.jsonl", pair_records)
        _write_jsonl(out_dir / "banking_news_review.jsonl", review)
        files["jsonl"] = ["banking_news_dataset.jsonl", "banking_news_article_stocks.jsonl",
                          "banking_news_review.jsonl"]
    if "sqlite" in formats and db.path:
        target = out_dir / "banking_news_dataset.sqlite"
        target.unlink(missing_ok=True)
        with sqlite3.connect(db.path) as source, sqlite3.connect(target) as copy:
            source.backup(copy)
        files["sqlite"] = [target.name]
    return {"articles": len(main), "pairs": len(pair_records), "review": len(review),
            "review_pairs": len(review_pairs),
            "unprocessed": len(unprocessed), "files": files}
