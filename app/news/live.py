"""Pemantauan berita live tanpa database.

Setiap putaran: baca news sitemap 7 portal, saring judul, unduh artikel baru, tentukan
relevansi per emiten, nilai sentimennya dengan IndoBERT, lalu simpan di memori proses.
Tidak ada yang ditulis ke disk; saat server berhenti, hasilnya hilang.
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.config import WIB
from app.dataset.config.keywords import PREFILTER
from app.dataset.services.extraction import NoContent, Paywalled, extract_article
from app.dataset.services.http import Blocked, FetchError, PoliteClient
from app.dataset.services.relevance import classify, target_sentences
from app.news.canonical import canonical_url
from app.news.model import Prediction
from app.news.sources import LIVE_SOURCES, LiveSource

log = logging.getLogger(__name__)

USER_AGENT = "web-stock-analyzer/0.1 (+local dashboard, reads public news sitemaps)"


@dataclass
class StockSentiment:
    label: str | None          # positif | netral | negatif | None (belum dinilai)
    confidence: float | None
    sentences: list[str]       # disimpan hanya sampai dinilai, lalu dikosongkan


@dataclass
class LiveArticle:
    key: str
    title: str
    url: str
    publisher: str
    published_at: datetime     # UTC
    fetched_at: datetime
    stocks: dict[str, StockSentiment]


@dataclass
class SourceState:
    key: str
    name: str
    homepage: str
    status: str = "pending"    # pending | ok | error
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    first_observed_at: datetime | None = None
    last_error: str | None = None
    last_item_count: int | None = None
    last_new_count: int | None = None


@dataclass
class Snapshot:
    articles: list[LiveArticle]
    observed_since: datetime | None
    earliest_article_at: datetime | None


@dataclass
class SitemapItem:
    url: str
    title: str
    published: datetime | None


_BLOCK = re.compile(r"<url>(.*?)</url>", re.S)


def _tag(block: str, name: str) -> str | None:
    m = re.search(rf"<{name}>\s*(?:<!\[CDATA\[)?\s*(.*?)\s*(?:\]\]>)?\s*</{name}>", block, re.S)
    return m.group(1).strip() if m else None


def parse_news_sitemap(xml: str) -> list[SitemapItem]:
    items = []
    for block in _BLOCK.findall(xml):
        loc = _tag(block, "loc")
        if not loc:
            continue
        raw_date = _tag(block, "news:publication_date") or _tag(block, "lastmod")
        published = None
        if raw_date:
            try:
                published = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            except ValueError:
                published = None
        items.append(SitemapItem(loc, _tag(block, "news:title") or "", published))
    return items


class LiveNewsService:
    def __init__(self, model, interval_seconds: int = 300, retention_days: int = 7,
                 sources: tuple[LiveSource, ...] = LIVE_SOURCES, client: PoliteClient | None = None,
                 min_content_chars: int = 400):
        self.model = model
        self.interval_seconds = interval_seconds
        self.retention = timedelta(days=retention_days)
        self.sources = sources
        self.client = client or PoliteClient(USER_AGENT, min_interval=2.0, timeout=25.0, max_retries=2)
        self.min_content_chars = min_content_chars
        self._lock = threading.RLock()
        self._articles: dict[str, LiveArticle] = {}
        # URL yang sudah diperiksa tetapi tidak relevan, agar tidak diunduh ulang tiap putaran.
        self._checked: dict[str, datetime] = {}
        self._states = {s.key: SourceState(s.key, s.portal.name, s.portal.homepage) for s in sources}
        self._round_lock = asyncio.Lock()
        self.last_run_finished_at: datetime | None = None
        self.next_run_at: datetime | None = None

    # ---------- Status ----------
    @property
    def running(self) -> bool:
        return self._round_lock.locked()

    def source_states(self) -> list[SourceState]:
        with self._lock:
            return [SourceState(**vars(state)) for state in self._states.values()]

    def snapshot(self) -> Snapshot:
        with self._lock:
            articles = list(self._articles.values())
            observed = [s.first_observed_at for s in self._states.values() if s.first_observed_at]
        return Snapshot(
            articles=articles,
            observed_since=min(observed) if observed else None,
            earliest_article_at=min((a.published_at for a in articles), default=None),
        )

    # ---------- Satu putaran ----------
    async def run_once(self) -> bool:
        """Jalankan satu putaran. False jika putaran lain sedang berjalan."""
        if self._round_lock.locked():
            return False
        async with self._round_lock:
            try:
                await asyncio.to_thread(self._poll_all)
            finally:
                self.last_run_finished_at = datetime.now(timezone.utc)
        return True

    async def run_forever(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception:
                log.exception("Putaran berita live gagal")
            self.next_run_at = datetime.now(timezone.utc) + timedelta(seconds=self.interval_seconds)
            await asyncio.sleep(self.interval_seconds)

    def _poll_all(self) -> None:
        # Portal berbeda domain, jadi bisa paralel; jeda per domain tetap dijaga PoliteClient.
        with ThreadPoolExecutor(max_workers=len(self.sources), thread_name_prefix="news") as pool:
            list(pool.map(self._poll_source, self.sources))
        self.score_pending()
        self._prune()

    def _poll_source(self, source: LiveSource) -> None:
        portal = source.portal
        state = self._states[source.key]
        attempt = datetime.now(timezone.utc)
        items: list[SitemapItem] = []
        errors = []
        for sitemap in source.sitemaps:
            try:
                items.extend(parse_news_sitemap(self.client.get_text(sitemap)))
            except FetchError as exc:
                errors.append(f"{sitemap.split('/')[2]}: {exc}")
        if errors and not items:
            with self._lock:
                state.status, state.last_attempt_at, state.last_error = "error", attempt, "; ".join(errors)[:300]
            return

        cutoff = attempt - self.retention
        new = 0
        for item in items:
            if not portal.article_pattern.search(item.url.split("?")[0]):
                continue
            if item.published and item.published.astimezone(timezone.utc) < cutoff - timedelta(days=1):
                continue
            if not PREFILTER.search(item.title or item.url.replace("-", " ")):
                continue
            key = canonical_url(item.url)
            with self._lock:
                if key in self._articles or key in self._checked:
                    continue
            try:
                if self._process(portal, item, key):
                    new += 1
            except Blocked as exc:
                errors.append(str(exc))
                break
            except Exception:
                log.exception("Artikel %s gagal diproses", item.url)

        with self._lock:
            state.last_attempt_at = attempt
            state.last_item_count = len(items)
            state.last_new_count = new
            if errors:
                state.status, state.last_error = "error", "; ".join(errors)[:300]
            else:
                state.status, state.last_error = "ok", None
                state.last_success_at = attempt
                state.first_observed_at = state.first_observed_at or attempt
        log.info("[%s] %d item sitemap, %d artikel relevan baru", source.key, len(items), new)

    def _process(self, portal, item: SitemapItem, key: str) -> bool:
        now = datetime.now(timezone.utc)
        try:
            html = self.client.get_text(portal.fetch_url(item.url.split("?")[0]))
            article = extract_article(html, item.url, self.min_content_chars, portal.extra_junk)
        except (NoContent, Paywalled, FetchError) as exc:
            if isinstance(exc, Blocked):
                raise
            if isinstance(exc, FetchError) and not exc.permanent:
                return False  # gangguan sementara: coba lagi di putaran berikutnya
            with self._lock:
                self._checked[key] = now
            return False

        published = article.published_at
        if published is None:
            with self._lock:
                self._checked[key] = now
            return False
        relevant = [m for m in classify(article.title, article.content) if m.relevance == "relevant"]
        if not relevant:
            with self._lock:
                self._checked[key] = now
            return False

        stocks = {}
        for match in relevant:
            sentences = target_sentences(match.code, article.title, article.content) or [article.title]
            prediction = self.model.predict(sentences)
            stocks[match.code] = _to_sentiment(prediction, sentences)
        live = LiveArticle(key, article.title, item.url.split("?")[0], portal.name,
                           published.astimezone(timezone.utc), now, stocks)
        with self._lock:
            self._articles[key] = live
        return True

    def score_pending(self) -> None:
        """Nilai artikel yang masuk sebelum model siap. Dipanggil tiap putaran dan saat model selesai dimuat."""
        if not self.model.ready:
            return
        with self._lock:
            pending = [(a, code, s) for a in self._articles.values() for code, s in a.stocks.items()
                       if s.label is None and s.sentences]
        for article, code, sentiment in pending:
            scored = _to_sentiment(self.model.predict(sentiment.sentences), sentiment.sentences)
            with self._lock:
                article.stocks[code] = scored

    def _prune(self) -> None:
        cutoff = datetime.now(timezone.utc) - self.retention
        with self._lock:
            for key in [k for k, a in self._articles.items() if a.published_at < cutoff]:
                del self._articles[key]
            for key in [k for k, t in self._checked.items() if t < cutoff]:
                del self._checked[key]


def _to_sentiment(prediction: Prediction | None, sentences: list[str]) -> StockSentiment:
    if prediction is None:
        return StockSentiment(None, None, sentences)
    # Setelah dinilai, teks tidak perlu disimpan lagi.
    return StockSentiment(prediction.label, prediction.confidence, [])


def wib(moment: datetime) -> str:
    return moment.astimezone(WIB).strftime("%d %b %Y %H:%M WIB")
