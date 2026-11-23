from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.market import service
from app.config import price_sync_enabled
from app.db import as_utc, get_session_factory
from app.market.models import PriceSyncStatus
from app.market.sync import PriceSyncer
from app.market.tickers import TICKER_CODES
from app.web.deps import check_range, get_price_syncer, get_session, valid_ticker
from app.web.schemas import CandleOut, MarketOut, PricesSyncOut, PriceStatusOut, TickerOut

router = APIRouter(prefix="/api", tags=["market"])


@router.get("/tickers", response_model=list[TickerOut])
def list_tickers(session: Session = Depends(get_session)):
    return [TickerOut(**summary.__dict__) for summary in service.ticker_summaries(session)]


@router.get("/market/{ticker}", response_model=MarketOut)
def market(
    ticker: str = Depends(valid_ticker),
    start: date | None = Query(None, description="ISO, inklusif"),
    end: date | None = Query(None, description="ISO, inklusif"),
    session: Session = Depends(get_session),
):
    check_range(start, end)
    full = service.market_history(session, ticker)
    candles = [
        c
        for c in full
        if (start is None or c.session_date >= start) and (end is None or c.session_date <= end)
    ]
    return MarketOut(
        ticker=ticker,
        start=start,
        end=end,
        first_date=full[0].session_date if full else None,
        last_date=full[-1].session_date if full else None,
        candles=[
            CandleOut(
                date=c.session_date,
                open=c.open,
                high=c.high,
                low=c.low,
                close=c.close,
                adj_close=c.adj_close,
                volume=c.volume,
                bb_upper=c.band.upper if c.band else None,
                bb_middle=c.band.middle if c.band else None,
                bb_lower=c.band.lower if c.band else None,
            )
            for c in candles
        ],
    )


def _prices_payload(syncer: PriceSyncer) -> PricesSyncOut:
    with get_session_factory()() as session:
        rows = {row.ticker: row for row in session.query(PriceSyncStatus).all()}
    tickers = []
    for code in TICKER_CODES:
        row = rows.get(code)
        tickers.append(
            PriceStatusOut(
                ticker=code,
                status=row.status if row else "pending",
                last_attempt_at=as_utc(row.last_attempt_at) if row else None,
                last_success_at=as_utc(row.last_success_at) if row else None,
                last_error=row.last_error if row else None,
                last_session_date=row.last_session_date if row else None,
                rows=row.rows if row else None,
                new_rows=row.new_rows if row else None,
                skipped_holidays=row.skipped_holidays if row else None,
                corrected_rows=row.corrected_rows if row else None,
            )
        )
    return PricesSyncOut(
        source="yahoo",
        syncing=syncer.running,
        auto_sync=price_sync_enabled(),
        interval_seconds=syncer.interval_seconds,
        last_run_finished_at=syncer.last_run_finished_at,
        next_run_at=syncer.next_run_at,
        tickers=tickers,
    )


@router.get("/prices/status", response_model=PricesSyncOut)
def prices_status(syncer: PriceSyncer = Depends(get_price_syncer)):
    return _prices_payload(syncer)


@router.post("/prices/sync", response_model=PricesSyncOut)
async def prices_sync(syncer: PriceSyncer = Depends(get_price_syncer)):
    """Ambil ulang histori dari Yahoo sekarang. Putaran yang sedang berjalan tidak ditumpuk."""
    await syncer.run_once()
    return _prices_payload(syncer)
