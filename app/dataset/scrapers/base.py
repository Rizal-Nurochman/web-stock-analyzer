"""Kerangka adapter portal dan helper penemuan URL yang dipakai bersama.

Setiap portal memilih jalur penemuan yang sah dan tersedia baginya:
- indeks per tanggal  (halaman "indeks" yang disediakan portal)
- sitemap             (sitemap bulanan/kuartalan/WordPress)
- daftar/tag          (halaman tag ticker, terbaru ke terlama)
- RSS                 (artikel terbaru)
Penemuan hanya menghasilkan kandidat; pengunduhan dan penyaringan ada di pipeline.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Callable, Iterator
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from app.dataset.models.types import Candidate
from app.dataset.services.http import Blocked, FetchError, PoliteClient

MONTHS = {
    "jan": 1, "januari": 1, "january": 1, "feb": 2, "februari": 2, "february": 2,
    "mar": 3, "maret": 3, "march": 3, "apr": 4, "april": 4, "mei": 5, "may": 5,
    "jun": 6, "juni": 6, "june": 6, "jul": 7, "juli": 7, "july": 7, "agu": 8, "agt": 8,
    "agustus": 8, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "okt": 10, "oktober": 10, "oct": 10, "october": 10, "nov": 11, "november": 11,
    "des": 12, "desember": 12, "dec": 12, "december": 12,
}
_TEXT_DATE = re.compile(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\.?\s+(20\d{2})\b")
_NUM_DATE = re.compile(r"\b(20\d{2})[-/](\d{2})[-/](\d{2})\b|\b(\d{2})/(\d{2})/(20\d{2})\b")


def parse_loose_date(text: str) -> date | None:
    """'13 November 2026', '12 Okt 2026', '2026-11-13', '13/11/2026'."""
    m = _TEXT_DATE.search(text)
    if m and m.group(2).lower() in MONTHS:
        try:
            return date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
        except ValueError:
            pass
    m = _NUM_DATE.search(text)
    if m:
        try:
            if m.group(1):
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return date(int(m.group(6)), int(m.group(5)), int(m.group(4)))
        except ValueError:
            return None
    return None


_URL_DATES = (
    re.compile(r"/(20\d{2})/(\d{2})/(\d{2})/"),                 # kompas /read/2023/03/15/
    re.compile(r"/(20\d{2})(\d{2})(\d{2})\d{6}-\d+-\d+/"),      # cnbc, cnn 20230315180143-78-
    re.compile(r"/(20\d{2})-(\d{2})-(\d{2})/"),                 # bareksa /2026-11-23/
)


def url_date(url: str) -> date | None:
    for pattern in _URL_DATES:
        m = pattern.search(url)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                return None
    return None


def iter_days(start: date, end: date) -> Iterator[date]:
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def slug_text(url: str) -> str:
    path = urlsplit(url).path.rstrip("/")
    return path.rsplit("/", 1)[-1].replace("-", " ")


@dataclass
class DiscoveryContext:
    source: str
    client: PoliteClient
    start: date
    end: date
    checkpoint_done: Callable[[str], bool]
    complete_checkpoint: Callable[[str, int], None]
    log: logging.Logger
    max_units: int | None = None
    units_done: int = 0
    stats: dict = field(default_factory=dict)

    def budget_left(self) -> bool:
        return self.max_units is None or self.units_done < self.max_units

    def bump(self, key: str, n: int = 1) -> None:
        self.stats[key] = self.stats.get(key, 0) + n


def links_in(html: str, base_url: str, pattern: re.Pattern[str]) -> dict[str, tuple[str, date | None]]:
    """Tautan artikel beserta teks jangkar terpanjang dan tanggal terdekat di daftar."""
    soup = BeautifulSoup(html, "lxml")
    found: dict[str, tuple[str, date | None]] = {}
    for a in soup.find_all("a", href=True):
        # Query string di tautan daftar hanya pelacak (tag_from, source, ...).
        href = urljoin(base_url, a["href"]).split("#")[0].split("?")[0]
        if not pattern.search(href):
            continue
        text = " ".join(a.get_text(" ", strip=True).split())
        when = None
        node = a
        for _ in range(4):  # tanggal biasanya ada di elemen pembungkus item
            node = node.parent
            if node is None:
                break
            when = parse_loose_date(node.get_text(" ", strip=True)[:400])
            if when:
                break
        old = found.get(href)
        if old is None or len(text) > len(old[0]):
            found[href] = (text, when or (old[1] if old else None))
    return found


class Portal:
    key: str = ""
    name: str = ""
    homepage: str = ""
    access_method: str = ""
    # Catatan cakupan yang jujur, tampil di laporan sumber.
    coverage_note: str | None = None
    # Diisi untuk portal yang diketahui menolak akses otomatis.
    blocked_reason: str | None = None
    article_pattern: re.Pattern[str] = re.compile(r"$^")
    extra_junk: re.Pattern[str] | None = None

    def discover(self, ctx: DiscoveryContext) -> Iterator[Candidate]:
        raise NotImplementedError

    def fetch_url(self, url: str) -> str:
        return url

    def category_from_url(self, url: str) -> str | None:
        parts = [p for p in urlsplit(url).path.split("/") if p]
        return parts[0] if parts else None

    def check(self, client: PoliteClient) -> tuple[str, str]:
        """Periksa akses saat ini. Kembalikan (status, catatan)."""
        if not client.allowed(self.homepage):
            return "unavailable", "robots.txt melarang halaman utama"
        try:
            client.get(self.homepage)
        except Blocked as exc:
            return "unavailable", f"{exc}. Tidak diakali sesuai kebijakan."
        except FetchError as exc:
            return "unavailable", f"Tidak dapat diakses: {exc}"
        if self.blocked_reason:
            return "unavailable", self.blocked_reason
        return ("partial" if self.coverage_note else "available"), (self.coverage_note or "")

    # ---------- Helper penemuan ----------
    def date_index(self, ctx: DiscoveryContext, url_for: Callable[[date, int], str],
                   max_pages: int = 30, paginate: bool = True, via: str = "indeks") -> Iterator[Candidate]:
        for day in iter_days(ctx.start, ctx.end):
            unit = f"{via}:{day.isoformat()}"
            if ctx.checkpoint_done(unit):
                continue
            if not ctx.budget_left():
                return
            seen: set[str] = set()
            failed = False
            for page in range(1, (max_pages if paginate else 1) + 1):
                url = url_for(day, page)
                try:
                    html = ctx.client.get_text(url)
                except FetchError as exc:
                    if isinstance(exc, Blocked):
                        raise
                    if page > 1 and exc.status == 404:
                        break  # beberapa portal membalas 404 setelah halaman terakhir
                    ctx.log.warning("%s gagal: %s", url, exc)
                    # Halaman pertama gagal: tanggal ini belum selesai, coba lagi saat resume.
                    failed = page == 1 or not exc.permanent
                    break
                links = links_in(html, url, self.article_pattern)
                fresh = {u: v for u, v in links.items() if u not in seen}
                if not fresh:
                    break
                seen.update(fresh)
                for link, (title, _) in fresh.items():
                    yield Candidate(link, title or None, url_date(link) or day, via,
                                    self.category_from_url(link))
            ctx.units_done += 1
            if failed:
                ctx.bump("units_failed")
                continue
            ctx.complete_checkpoint(unit, len(seen))
            ctx.log.info("[%s] %s: %d tautan", self.key, unit, len(seen))

    def sitemap_entries(self, ctx: DiscoveryContext, url: str) -> list[tuple[str, date | None, str | None]]:
        xml = ctx.client.get_text(url)
        entries = []
        for block in re.findall(r"<(?:url|sitemap)>(.*?)</(?:url|sitemap)>", xml, re.S):
            loc = re.search(r"<loc>\s*(?:<!\[CDATA\[)?\s*(.*?)\s*(?:\]\]>)?\s*</loc>", block, re.S)
            if not loc:
                continue
            when_raw = re.search(
                r"<(?:news:publication_date|lastmod)>\s*(?:<!\[CDATA\[)?\s*([^<\]]+?)\s*(?:\]\]>)?\s*</", block)
            title = re.search(r"<news:title>\s*(?:<!\[CDATA\[)?\s*(.*?)\s*(?:\]\]>)?\s*</news:title>", block, re.S)
            when = None
            if when_raw:
                try:
                    when = datetime.fromisoformat(when_raw.group(1).replace("Z", "+00:00")).date()
                except ValueError:
                    when = parse_loose_date(when_raw.group(1))
            entries.append((loc.group(1).strip(), when, title.group(1).strip() if title else None))
        return entries

    def sitemap(self, ctx: DiscoveryContext, sitemap_urls: list[str], via: str = "sitemap",
                lastmod_is_publish: bool = False, final: Callable[[str], bool] = lambda u: True
                ) -> Iterator[Candidate]:
        """Telusuri file sitemap. lastmod >= tanggal terbit, jadi lastmod < start aman dilewati."""
        for sm in sitemap_urls:
            unit = f"{via}:{sm}"
            if ctx.checkpoint_done(unit):
                continue
            if not ctx.budget_left():
                return
            try:
                entries = self.sitemap_entries(ctx, sm)
            except FetchError as exc:
                if isinstance(exc, Blocked):
                    raise
                ctx.log.warning("%s gagal: %s", sm, exc)
                continue
            count = 0
            for loc, when, title in entries:
                if not self.article_pattern.search(loc):
                    continue
                if when and when < ctx.start:
                    continue
                if lastmod_is_publish and when and when > ctx.end:
                    continue
                count += 1
                yield Candidate(loc, title, url_date(loc) or (when if lastmod_is_publish else None),
                                via, self.category_from_url(loc))
            ctx.units_done += 1
            if final(sm):
                ctx.complete_checkpoint(unit, count)
            ctx.log.info("[%s] %s: %d kandidat", self.key, unit, count)

    def listing(self, ctx: DiscoveryContext, url_for_page: Callable[[int], str], via: str,
                max_pages: int = 400, prefilter: bool = False) -> Iterator[Candidate]:
        """Daftar terbaru-ke-terlama (tag ticker). Berhenti saat seluruh item lebih tua dari start."""
        seen: set[str] = set()
        for page in range(1, max_pages + 1):
            if not ctx.budget_left():
                return
            url = url_for_page(page)
            try:
                html = ctx.client.get_text(url)
            except FetchError as exc:
                if isinstance(exc, Blocked):
                    raise
                ctx.log.warning("%s gagal: %s", url, exc)
                return
            links = {u: v for u, v in links_in(html, url, self.article_pattern).items() if u not in seen}
            ctx.units_done += 1
            if not links:
                return
            seen.update(links)
            dated = [d for _, d in links.values() if d]
            for link, (title, when) in links.items():
                when = url_date(link) or when
                if when and (when < ctx.start or when > ctx.end):
                    continue
                yield Candidate(link, title or None, when, via, self.category_from_url(link), prefilter)
            if dated and max(dated) < ctx.start:
                ctx.log.info("[%s] %s: melewati awal periode di halaman %d", self.key, via, page)
                return

    def rss(self, ctx: DiscoveryContext, feeds: list[str], via: str = "rss") -> Iterator[Candidate]:
        from app.news.parser import FeedParseError, parse_feed

        for feed in feeds:
            try:
                items = parse_feed(ctx.client.get_text(feed))
            except (FetchError, FeedParseError) as exc:
                if isinstance(exc, Blocked):
                    raise
                ctx.log.warning("%s gagal: %s", feed, exc)
                continue
            for item in items:
                when = item.published_at.date() if item.published_at else None
                if when and (when < ctx.start or when > ctx.end):
                    continue
                if self.article_pattern.search(item.link):
                    yield Candidate(item.link, item.title, when, via, self.category_from_url(item.link))


def sitemap_children(ctx: DiscoveryContext, index_url: str, pattern: re.Pattern[str]) -> list[str]:
    xml = ctx.client.get_text(index_url)
    locs = re.findall(r"<loc>\s*(?:<!\[CDATA\[)?\s*(.*?)\s*(?:\]\]>)?\s*</loc>", xml, re.S)
    return [loc.strip() for loc in locs if pattern.search(loc)]


def month_starts(start: date, end: date) -> Iterator[date]:
    current = date(start.year, start.month, 1)
    while current <= end:
        yield current
        current = date(current.year + (current.month == 12), current.month % 12 + 1, 1)


class UnavailablePortal(Portal):
    """Portal yang menolak akses otomatis. Hanya diperiksa, tidak di-scrape."""

    access_method = "Tidak terintegrasi"

    def discover(self, ctx: DiscoveryContext) -> Iterator[Candidate]:
        ctx.log.warning("[%s] dilewati: %s", self.key, self.blocked_reason)
        return iter(())

    def check(self, client: PoliteClient) -> tuple[str, str]:
        try:
            client.get(self.homepage)
        except Blocked as exc:
            return "unavailable", f"{exc}. {self.blocked_reason}"
        except FetchError as exc:
            return "unavailable", f"{exc}. {self.blocked_reason}"
        return "unavailable", (
            "Halaman utama kini bisa diakses, tetapi adapter belum diverifikasi terhadap struktur "
            f"situsnya. {self.blocked_reason}"
        )
