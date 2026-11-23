"""Sinkronisasi histori harga dari Yahoo Finance ke tabel prices.

Pemakaian manual:
    python -m app.market.sync
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import utcnow
from app.market.importer import import_rows
from app.market.models import Price, PriceSyncStatus
from app.market.tickers import TICKER_CODES
from app.market.yahoo import YahooError, YahooHistory, fetch_history

log = logging.getLogger(__name__)

# Jika Yahoo tiba-tiba mengirim jauh lebih sedikit sesi dari yang tersimpan, anggap respons
# rusak dan pertahankan data lama, alih-alih menghapus histori.
MIN_KEEP_RATIO = 0.8
# Jeda antaremiten agar tidak memicu pembatasan Yahoo.
REQUEST_GAP_SECONDS = 1.0


@dataclass
class PriceResult:
    ticker: str
    ok: bool
    rows: int = 0
    new_rows: int = 0
    error: str | None = None


def _describe(exc: Exception) -> str:
    if isinstance(exc, YahooError):
        return str(exc)
    if isinstance(exc, httpx.TimeoutException):
        return "Waktu permintaan ke Yahoo habis"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"Yahoo membalas HTTP {exc.response.status_code}"
    if isinstance(exc, httpx.TransportError):
        return "Tidak dapat terhubung ke Yahoo Finance"
    return f"{type(exc).__name__}: {exc}"[:300]


def store_history(session: Session, ticker: str, history: YahooHistory, attempt_at: datetime) -> PriceResult:
    stored = session.scalar(select(func.count()).select_from(Price).where(Price.ticker == ticker)) or 0
    if stored and len(history.rows) < stored * MIN_KEEP_RATIO:
        raise YahooError(
            f"Yahoo hanya mengirim {len(history.rows)} sesi, padahal tersimpan {stored}. Data lama dipertahankan"
        )

    result = import_rows(session, history.rows, source="yahoo")
    dates = {row.session_date for row in history.rows}
    stale = [
        day
        for day in session.scalars(select(Price.session_date).where(Price.ticker == ticker))
        if day not in dates
    ]
    if stale:
        session.execute(delete(Price).where(Price.ticker == ticker, Price.session_date.in_(stale)))

    status = session.get(PriceSyncStatus, ticker) or PriceSyncStatus(ticker=ticker)
    status.status = "ok"
    status.last_attempt_at = attempt_at
    status.last_success_at = attempt_at
    status.last_error = None
    status.last_session_date = max(dates)
    status.rows = len(history.rows)
    status.new_rows = result.inserted
    status.skipped_holidays = history.skipped_holidays
    status.corrected_rows = history.corrected_rows
    session.add(status)
    session.flush()
    return PriceResult(ticker, True, len(history.rows), result.inserted)


def mark_failed(session: Session, ticker: str, attempt_at: datetime, error: str) -> None:
    status = session.get(PriceSyncStatus, ticker) or PriceSyncStatus(ticker=ticker)
    status.status = "error"
    status.last_attempt_at = attempt_at
    status.last_error = error
    session.add(status)
    session.flush()


class PriceSyncer:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        tickers: tuple[str, ...] = TICKER_CODES,
        interval_seconds: int = 3600,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
        request_gap: float = REQUEST_GAP_SECONDS,
    ):
        self.session_factory = session_factory
        self.tickers = tickers
        self.interval_seconds = interval_seconds
        self.client_factory = client_factory or httpx.AsyncClient
        self.request_gap = request_gap
        self._lock = asyncio.Lock()
        self.last_run_finished_at: datetime | None = None
        self.next_run_at: datetime | None = None

    @property
    def running(self) -> bool:
        return self._lock.locked()

    def _write(self, fn, *args):
        session = self.session_factory()
        try:
            out = fn(session, *args)
            session.commit()
            return out
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    async def _sync_ticker(self, client: httpx.AsyncClient, ticker: str) -> PriceResult:
        attempt_at = utcnow()
        try:
            history = await fetch_history(client, ticker)
            return await asyncio.to_thread(self._write, store_history, ticker, history, attempt_at)
        except Exception as exc:  # satu emiten gagal tidak menghentikan emiten lain
            error = _describe(exc)
            log.warning("Harga %s gagal diperbarui: %s", ticker, error)
            await asyncio.to_thread(self._write, mark_failed, ticker, attempt_at, error)
            return PriceResult(ticker, False, error=error)

    async def run_once(self) -> list[PriceResult] | None:
        if self._lock.locked():
            return None
        async with self._lock:
            results = []
            try:
                async with self.client_factory() as client:
                    for index, ticker in enumerate(self.tickers):
                        if index:
                            await asyncio.sleep(self.request_gap)
                        results.append(await self._sync_ticker(client, ticker))
                return results
            finally:
                self.last_run_finished_at = utcnow()

    async def run_forever(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception:
                log.exception("Putaran sinkronisasi harga gagal")
            self.next_run_at = utcnow() + timedelta(seconds=self.interval_seconds)
            await asyncio.sleep(self.interval_seconds)


def main() -> int:
    from app.db import get_session_factory

    results = asyncio.run(PriceSyncer(get_session_factory()).run_once()) or []
    for r in results:
        line = f"  {r.ticker}: {r.rows} sesi, {r.new_rows} baru" if r.ok else f"  {r.ticker}: GAGAL, {r.error}"
        print(line)
    return 0 if results and all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
