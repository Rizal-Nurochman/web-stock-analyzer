"""Pembacaan berita live dari memori: daftar terbaru dan jendela per sesi."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.config import IDX_SESSION_CLOSE, WIB
from app.market.service import previous_session
from app.news.live import LiveArticle, LiveNewsService, Snapshot, wib


@dataclass(frozen=True)
class ArticleView:
    id: str
    title: str
    url: str
    publisher: str
    published_at: datetime
    sentiment: str
    confidence: float | None


@dataclass(frozen=True)
class SessionWindow:
    start: datetime
    end: datetime


SENTIMENT_KEYS = ("positif", "netral", "negatif", "belum_dinilai")


@dataclass(frozen=True)
class NewsResult:
    status: str  # ok | empty | partial | unavailable
    reason: str | None
    articles: list[ArticleView]
    snapshot: Snapshot
    window: SessionWindow | None = None
    previous_session: date | None = None
    # Jumlah per label atas SEMUA artikel emiten dalam cakupan, bukan hanya yang dikirim.
    summary: dict[str, int] | None = None


def sentiment_summary(articles: list[LiveArticle], ticker: str) -> dict[str, int]:
    counts = dict.fromkeys(SENTIMENT_KEYS, 0)
    for article in articles:
        stock = article.stocks.get(ticker)
        if stock is not None:
            counts[stock.label or "belum_dinilai"] += 1
    return counts


def session_close_utc(day: date) -> datetime:
    return datetime.combine(day, IDX_SESSION_CLOSE, tzinfo=WIB).astimezone(timezone.utc)


def _views(articles: list[LiveArticle], ticker: str, limit: int) -> list[ArticleView]:
    chosen = sorted((a for a in articles if ticker in a.stocks), key=lambda a: a.published_at, reverse=True)
    return [
        ArticleView(a.key, a.title, a.url, a.publisher, a.published_at,
                    a.stocks[ticker].label or "belum_dinilai", a.stocks[ticker].confidence)
        for a in chosen[:limit]
    ]


def latest_news(live: LiveNewsService, ticker: str, limit: int = 30) -> NewsResult:
    snap = live.snapshot()
    articles = _views(snap.articles, ticker, limit)
    if articles:
        return NewsResult("ok", None, articles, snap, summary=sentiment_summary(snap.articles, ticker))
    if snap.observed_since is None:
        return NewsResult("unavailable", "Pemantauan berita belum menyelesaikan putaran pertama.", [], snap)
    return NewsResult("empty", "Belum ada artikel yang relevan dengan emiten ini sejak pemantauan dimulai.",
                      [], snap)


def session_news(live: LiveNewsService, session: Session, ticker: str, session_date: date,
                 limit: int = 50) -> NewsResult:
    snap = live.snapshot()
    prev = previous_session(session, ticker, session_date)
    if prev is None:
        return NewsResult("unavailable",
                          "Batas sesi sebelumnya tidak tersedia karena ini sesi pertama dalam data harga.",
                          [], snap)
    window = SessionWindow(session_close_utc(prev), session_close_utc(session_date))
    if snap.observed_since is None or snap.earliest_article_at is None:
        return NewsResult("unavailable", "Pemantauan berita belum menyelesaikan putaran pertama.",
                          [], snap, window, prev)
    if window.end <= snap.earliest_article_at:
        return NewsResult(
            "unavailable",
            f"Berita hanya disimpan di memori sejak server berjalan; artikel tertua {wib(snap.earliest_article_at)}.",
            [], snap, window, prev)

    in_window = [a for a in snap.articles if window.start < a.published_at <= window.end]
    articles = _views(in_window, ticker, limit)
    summary = sentiment_summary(in_window, ticker) if articles else None
    if window.start < snap.observed_since:
        reason = (f"Pemantauan dimulai {wib(snap.observed_since)}. Sebelum itu hanya artikel yang masih "
                  "tercantum di news sitemap yang tertangkap.")
        return NewsResult("partial", reason, articles, snap, window, prev, summary)
    if not articles:
        return NewsResult("empty", "Tidak ada artikel tentang emiten ini dalam jendela sesi.",
                          [], snap, window, prev)
    return NewsResult("ok", None, articles, snap, window, prev, summary)
