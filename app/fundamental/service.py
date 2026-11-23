"""Cache fundamental di memori proses. Tidak ada yang ditulis ke database.

Laporan keuangan hanya berubah per kuartal, sedangkan rasio harga berubah tiap hari bursa,
jadi satu pengambilan dipakai ulang selama TTL. Bila Yahoo gagal, data lama tetap
disajikan dengan penanda stale beserta pesan galatnya.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.fundamental.metrics import compute
from app.fundamental.yahoo import YahooFundamentalClient
from app.market.yahoo import YahooError

log = logging.getLogger(__name__)


@dataclass
class _Entry:
    data: dict | None = None
    fetched_at: datetime | None = None
    error: str | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class FundamentalService:
    def __init__(self, client: YahooFundamentalClient | None = None, ttl_seconds: int = 6 * 3600):
        self.client = client or YahooFundamentalClient()
        self.ttl = timedelta(seconds=ttl_seconds)
        self._entries: dict[str, _Entry] = {}

    def _fresh(self, entry: _Entry, now: datetime) -> bool:
        return entry.data is not None and entry.fetched_at is not None and now - entry.fetched_at < self.ttl

    async def get(self, ticker: str, refresh: bool = False) -> dict:
        entry = self._entries.setdefault(ticker, _Entry())
        async with entry.lock:
            now = datetime.now(timezone.utc)
            if refresh or not self._fresh(entry, now):
                try:
                    entry.data = compute(**await self.client.fetch(ticker))
                    entry.fetched_at = now
                    entry.error = None
                except (YahooError, ValueError, KeyError, OSError) as exc:
                    entry.error = str(exc) or exc.__class__.__name__
                    log.warning("Fundamental %s gagal diambil: %s", ticker, entry.error)
                except Exception as exc:  # httpx.HTTPError dan sejenisnya
                    entry.error = f"Yahoo tidak dapat dihubungi ({exc.__class__.__name__})"
                    log.warning("Fundamental %s gagal diambil: %r", ticker, exc)
            return {
                "ticker": ticker,
                "status": "ok" if entry.error is None else ("stale" if entry.data else "unavailable"),
                "error": entry.error,
                "fetched_at": entry.fetched_at.isoformat() if entry.fetched_at else None,
                "ttl_seconds": int(self.ttl.total_seconds()),
                "source": "yahoo",
                **(entry.data or {}),
            }

    async def aclose(self) -> None:
        await self.client.aclose()
