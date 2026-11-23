"""Orkestrasi pengumpulan: penemuan -> prafilter -> unduh -> ekstraksi -> relevansi ->
deduplikasi -> simpan. Satu portal gagal tidak menghentikan portal lain."""

from __future__ import annotations

import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, time

from sqlalchemy.exc import IntegrityError

from app.config import WIB
from app.dataset.config import Settings
from app.dataset.config.keywords import PREFILTER
from app.dataset.database.repository import Repository
from app.dataset.database.session import Database
from app.dataset.models.schema import Article, ArticleStock, now_wib_iso
from app.dataset.models.types import Candidate
from app.dataset.scrapers import get_portal
from app.dataset.scrapers.base import DiscoveryContext, Portal, slug_text
from app.dataset.services import dedup, relevance
from app.dataset.services.extraction import NoContent, Paywalled, extract_article
from app.dataset.services.http import Blocked, FetchError, PoliteClient, RobotsDisallowed
from app.news.canonical import canonical_url

log = logging.getLogger("dataset")


@dataclass
class SourceStats:
    source: str
    status: str = "pending"
    note: str = ""
    discovered: int = 0
    prefiltered_out: int = 0
    already_seen: int = 0
    out_of_range: int = 0
    fetched: int = 0
    saved_relevant: int = 0
    saved_review: int = 0
    duplicates: int = 0
    irrelevant: int = 0
    no_content: int = 0
    paywalled: int = 0
    not_indonesian: int = 0
    robots_disallowed: int = 0
    failed: int = 0
    blocked: int = 0
    stopped_early: str | None = None


class SourceBlocked(Exception):
    pass


class Collector:
    def __init__(self, settings: Settings, db: Database, client: PoliteClient | None = None):
        self.settings = settings
        self.db = db
        self.repo = Repository(db)
        self.client = client or PoliteClient(
            settings.user_agent, settings.min_interval, settings.timeout, settings.max_retries)

    # ---------- Pemeriksaan sumber ----------
    def check_sources(self, keys: list[str]) -> list[tuple[Portal, str, str]]:
        results = []
        for key in keys:
            portal = get_portal(key)
            status, note = portal.check(self.client)
            self.repo.set_source_status(key, portal.name, status, portal.access_method, note)
            results.append((portal, status, note))
            log.info("[%s] %s %s", key, status, note)
        return results

    # ---------- Pengumpulan ----------
    def run(self, keys: list[str]) -> list[SourceStats]:
        run_id = self.repo.start_run({
            "sources": keys, "start": self.settings.start, "end": self.settings.end,
            "max_articles_per_source": self.settings.max_articles_per_source,
            "max_units_per_source": self.settings.max_units_per_source,
        })
        results: list[SourceStats] = []
        workers = max(1, min(self.settings.parallel_sources, len(keys)))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="portal") as pool:
            futures = {pool.submit(self.run_source, key): key for key in keys}
            for future in as_completed(futures):
                key = futures[future]
                try:
                    results.append(future.result())
                except Exception as exc:  # cadangan: kesalahan tak terduga di satu portal
                    log.exception("[%s] berhenti karena kesalahan", key)
                    results.append(SourceStats(key, status="error", note=str(exc)[:300]))
        order = {k: i for i, k in enumerate(keys)}
        results.sort(key=lambda s: order.get(s.source, 99))
        self.repo.finish_run(run_id, {s.source: asdict(s) for s in results})
        return results

    def run_source(self, key: str) -> SourceStats:
        portal = get_portal(key)
        stats = SourceStats(key)
        status, note = portal.check(self.client)
        self.repo.set_source_status(key, portal.name, status, portal.access_method, note)
        stats.status, stats.note = status, note
        if status == "unavailable":
            log.warning("[%s] tidak tersedia: %s", key, note)
            return stats

        ctx = DiscoveryContext(
            source=key, client=self.client, start=self.settings.start, end=self.settings.end,
            checkpoint_done=lambda unit: self.repo.checkpoint_done(key, unit),
            complete_checkpoint=lambda unit, n: self.repo.complete_checkpoint(key, unit, n),
            log=log, max_units=self.settings.max_units_per_source,
        )
        consecutive_blocks = 0
        limit = self.settings.max_articles_per_source
        try:
            for candidate in portal.discover(ctx):
                stats.discovered += 1
                try:
                    self.process(portal, candidate, stats)
                    consecutive_blocks = 0
                except SourceBlocked:
                    consecutive_blocks += 1
                    if consecutive_blocks >= self.settings.max_consecutive_blocks:
                        stats.stopped_early = "diblokir berturut-turut"
                        break
                if limit and stats.saved_relevant + stats.saved_review >= limit:
                    stats.stopped_early = f"batas {limit} artikel tercapai"
                    break
                if stats.discovered % 200 == 0:
                    log.info("[%s] progres: %s", key, _brief(stats))
        except Blocked as exc:
            stats.stopped_early = f"penemuan diblokir: {exc}"
            self.repo.set_source_status(key, portal.name, "unavailable", portal.access_method, str(exc))
        if stats.blocked and not (stats.saved_relevant or stats.saved_review):
            stats.status = "unavailable"
        log.info("[%s] selesai: %s", key, _brief(stats))
        return stats

    def _mark(self, portal: Portal, candidate: Candidate, canonical: str, status: str,
              stats: SourceStats, reason: str | None = None, title: str | None = None) -> None:
        self.repo.mark_seen(canonical, portal.key, candidate.url, status, reason, title or candidate.title)
        attr = {"robots_disallowed": "robots_disallowed", "not_indonesian": "not_indonesian"}.get(status, status)
        if hasattr(stats, attr) and attr not in ("saved",):
            setattr(stats, attr, getattr(stats, attr) + 1)

    def process(self, portal: Portal, candidate: Candidate, stats: SourceStats) -> None:
        s = self.settings
        canonical = canonical_url(candidate.url)
        hint = candidate.published_hint
        if hint and not (s.start <= hint <= s.end):
            stats.out_of_range += 1
            return
        if candidate.prefilter and not PREFILTER.search(f"{candidate.title or ''} {slug_text(candidate.url)}"):
            stats.prefiltered_out += 1
            return
        if self.repo.should_skip(canonical):
            stats.already_seen += 1
            return

        try:
            html = self.client.get_text(portal.fetch_url(candidate.url))
        except RobotsDisallowed as exc:
            self._mark(portal, candidate, canonical, "robots_disallowed", stats, str(exc))
            return
        except Blocked as exc:
            self._mark(portal, candidate, canonical, "blocked", stats, str(exc))
            raise SourceBlocked(str(exc)) from exc
        except FetchError as exc:
            self._mark(portal, candidate, canonical, "failed", stats, str(exc))
            return
        stats.fetched += 1

        try:
            article = extract_article(html, candidate.url, s.min_content_chars, portal.extra_junk,
                                      candidate.category)
        except Paywalled as exc:
            self._mark(portal, candidate, canonical, "paywalled", stats, str(exc))
            return
        except NoContent as exc:
            self._mark(portal, candidate, canonical, "no_content", stats, str(exc))
            return
        except Exception as exc:  # HTML rusak atau tak terduga
            self._mark(portal, candidate, canonical, "failed", stats, f"ekstraksi: {exc}"[:300])
            return

        published = article.published_at or (datetime.combine(hint, time(0), WIB) if hint else None)
        if published and not (s.start <= published.date() <= s.end):
            self._mark(portal, candidate, canonical, "out_of_range", stats,
                       f"terbit {published.date()}", article.title)
            return
        if article.language != "id":
            self._mark(portal, candidate, canonical, "not_indonesian", stats, article.language, article.title)
            return

        matches = relevance.classify(article.title, article.content)
        status = relevance.article_status(matches)
        if status is None:
            self._mark(portal, candidate, canonical, "irrelevant", stats, "tidak menyebut empat emiten",
                       article.title)
            return
        if published is None:
            status = "review"
            for m in matches:
                m.relevance = "review"
                m.reasons.append("tanggal terbit tidak ditemukan")

        article_id = f"{portal.key}-{hashlib.sha1(article.canonical_url.encode()).hexdigest()[:12]}"
        chash = dedup.content_hash(article.content)
        row = Article(
            article_id=article_id,
            title=article.title,
            content=article.content,
            source=portal.name,
            url=candidate.url,
            canonical_url=article.canonical_url,
            author=article.author,
            published_at=published.replace(microsecond=0).isoformat() if published else None,
            scraped_at=now_wib_iso(),
            category=article.category,
            language=article.language,
            content_hash=chash,
            title_key=dedup.title_key(article.title),
            word_count=len(article.content.split()),
            relevance_status=status,
            discovered_via=candidate.discovered_via,
        )
        stocks = [
            ArticleStock(
                stock_code=m.code, stock_name=m.name, relevance=m.relevance,
                relevance_score=m.score, mention_count=m.mention_count, in_title=m.in_title,
                matched_terms="; ".join(m.matched_terms), relevance_reasons="; ".join(m.reasons),
                review_status="unreviewed",
            )
            for m in matches
        ]

        # Deteksi duplikasi dan penyimpanan dalam satu kunci agar dua portal paralel
        # tidak saling melewatkan sindikasi.
        with self.db.write_lock:
            neighbours = []
            if published:
                low, high = dedup.window_bounds(published)
                neighbours = self.repo.articles_near(low, high)
            match = dedup.find_duplicate(article.content, article.title, published,
                                         self.repo.find_by_hash(chash), neighbours)
            if match:
                row.duplicate_group_id = match.group_id
                row.is_duplicate = True
                row.duplicate_reason = match.reason
            try:
                self.repo.save_article(row, stocks)
            except IntegrityError:
                # Artikel yang sama sudah tersimpan lewat alias URL lain (redirect, rel=canonical).
                self.repo.mark_seen(canonical, portal.key, candidate.url, "saved",
                                    "URL kanonis sudah tersimpan", article.title)
                stats.already_seen += 1
                return
            if match:
                self.repo.set_group(match.other_article_id, match.group_id)
                stats.duplicates += 1

        self.repo.mark_seen(canonical, portal.key, candidate.url, "saved", status, article.title)
        if article.canonical_url != canonical:
            self.repo.mark_seen(article.canonical_url, portal.key, candidate.url, "saved", status, article.title)
        if status == "relevant":
            stats.saved_relevant += 1
        else:
            stats.saved_review += 1
        log.info("[%s] %s %s | %s", portal.key, status.upper(),
                 ",".join(f"{m.code}:{m.relevance[:3]}" for m in matches), article.title[:90])


def _brief(stats: SourceStats) -> str:
    return (f"ditemukan {stats.discovered}, diunduh {stats.fetched}, relevan {stats.saved_relevant}, "
            f"review {stats.saved_review}, tidak relevan {stats.irrelevant}, "
            f"gagal {stats.failed + stats.no_content + stats.paywalled}")
