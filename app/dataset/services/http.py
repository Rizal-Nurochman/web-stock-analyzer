"""Klien HTTP yang sopan: robots.txt, jeda per domain, retry terbatas, deteksi blokir.

Klien ini sengaja tidak mencoba melewati proteksi. Respons 401/403/451 atau halaman
tantangan Cloudflare dilaporkan sebagai Blocked dan portal ditandai tidak tersedia.
"""

from __future__ import annotations

import logging
import threading
import time
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

log = logging.getLogger(__name__)

CHALLENGE_MARKERS = ("cf-chl", "Just a moment...", "challenge-platform", "Attention Required!")
MULTI_PART_SUFFIXES = (".co.id", ".or.id", ".go.id", ".ac.id", ".web.id", ".my.id")


class FetchError(Exception):
    def __init__(self, message: str, permanent: bool = False, status: int | None = None):
        super().__init__(message)
        self.permanent = permanent
        self.status = status


class Blocked(FetchError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message, permanent=True, status=status)


class RobotsDisallowed(FetchError):
    def __init__(self, url: str):
        super().__init__(f"Dilarang robots.txt: {url}", permanent=True)


def site_key(host: str) -> str:
    """investasi.kontan.co.id dan www.kontan.co.id berbagi batas laju yang sama."""
    host = host.lower()
    parts = host.split(".")
    keep = 3 if host.endswith(MULTI_PART_SUFFIXES) else 2
    return ".".join(parts[-keep:])


class PoliteClient:
    def __init__(self, user_agent: str, min_interval: float = 2.0, timeout: float = 25.0,
                 max_retries: int = 3, transport: httpx.BaseTransport | None = None,
                 sleep=time.sleep):
        self.user_agent = user_agent
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.sleep = sleep
        self.client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Language": "id-ID,id;q=0.9,en;q=0.5"},
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        )
        self._robots: dict[str, RobotFileParser] = {}
        self._robots_lock = threading.Lock()
        self._next_at: dict[str, float] = {}
        self._site_locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        self.request_count = 0

    def close(self) -> None:
        self.client.close()

    # ---------- robots.txt ----------
    def _robots_for(self, url: str) -> RobotFileParser:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        with self._robots_lock:
            cached = self._robots.get(origin)
        if cached is not None:
            return cached
        parser = RobotFileParser()
        try:
            self._throttle(origin + "/robots.txt", 0.0)
            response = self.client.get(origin + "/robots.txt")
            self.request_count += 1
            if response.status_code >= 500:
                # RFC 9309: robots.txt tidak terjangkau berarti anggap semua dilarang.
                parser.parse(["User-agent: *", "Disallow: /"])
            elif response.status_code >= 400:
                parser.parse([])  # tidak ada robots.txt: semua diizinkan
            else:
                parser.parse(response.text.splitlines())
        except httpx.HTTPError:
            parser.parse(["User-agent: *", "Disallow: /"])
        with self._robots_lock:
            self._robots[origin] = parser
        return parser

    def allowed(self, url: str) -> bool:
        return self._robots_for(url).can_fetch(self.user_agent, url)

    def crawl_delay(self, url: str) -> float:
        delay = self._robots_for(url).crawl_delay(self.user_agent)
        return float(delay) if delay else 0.0

    # ---------- Jeda per domain ----------
    def _site_lock(self, key: str) -> threading.Lock:
        with self._locks_guard:
            return self._site_locks.setdefault(key, threading.Lock())

    def _throttle(self, url: str, extra_delay: float) -> None:
        key = site_key(urlsplit(url).hostname or "")
        interval = max(self.min_interval, extra_delay)
        with self._site_lock(key):
            wait = self._next_at.get(key, 0.0) - time.monotonic()
            if wait > 0:
                self.sleep(wait)
            self._next_at[key] = time.monotonic() + interval

    # ---------- Permintaan ----------
    def get(self, url: str, check_robots: bool = True) -> httpx.Response:
        if check_robots and not self.allowed(url):
            raise RobotsDisallowed(url)
        delay = self.crawl_delay(url) if check_robots else 0.0
        last_error: FetchError | None = None
        for attempt in range(1, self.max_retries + 1):
            self._throttle(url, delay)
            try:
                response = self.client.get(url)
                self.request_count += 1
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = FetchError(f"{type(exc).__name__}: {exc}"[:200])
                self._backoff(attempt, None)
                continue

            status = response.status_code
            if status == 200:
                return response
            if status in (401, 403, 451):
                challenge = any(m in response.text[:5000] for m in CHALLENGE_MARKERS)
                kind = "tantangan bot (Cloudflare)" if challenge else "akses ditolak"
                raise Blocked(f"HTTP {status}: {kind}", status=status)
            if status in (404, 410):
                raise FetchError(f"HTTP {status}", permanent=True, status=status)
            if status == 429 or status >= 500:
                last_error = FetchError(f"HTTP {status}", status=status)
                self._backoff(attempt, response.headers.get("Retry-After"))
                continue
            raise FetchError(f"HTTP {status}", permanent=True, status=status)
        assert last_error is not None
        raise last_error

    def _backoff(self, attempt: int, retry_after: str | None) -> None:
        if attempt >= self.max_retries:
            return
        seconds = 2.0 * (2 ** (attempt - 1))
        if retry_after and retry_after.isdigit():
            seconds = max(seconds, min(float(retry_after), 120.0))
        log.info("Mencoba ulang dalam %.0f detik", seconds)
        self.sleep(seconds)

    def get_text(self, url: str, check_robots: bool = True) -> str:
        response = self.get(url, check_robots=check_robots)
        return response.text
