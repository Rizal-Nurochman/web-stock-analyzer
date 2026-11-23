"""Query histori harga. Band dihitung pada seri penuh sebelum filter tampilan."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.market.indicators import Band, bollinger_bands
from app.market.models import Price
from app.market.tickers import ISSUERS

SPARKLINE_POINTS = 160


@dataclass(frozen=True)
class Candle:
    session_date: date
    open: float
    high: float
    low: float
    close: float
    adj_close: float | None
    volume: int
    band: Band | None


@dataclass(frozen=True)
class TickerSummary:
    code: str
    name: str
    short_name: str
    first_date: date | None
    last_date: date | None
    rows: int
    source: str | None
    last_close: float | None
    prev_close: float | None
    sparkline: list[float]


def _load_series(session: Session, ticker: str) -> list[Price]:
    return list(
        session.scalars(
            select(Price).where(Price.ticker == ticker).order_by(Price.session_date)
        )
    )


def _downsample(values: list[float], points: int) -> list[float]:
    if len(values) <= points:
        return values
    step = (len(values) - 1) / (points - 1)
    return [values[round(i * step)] for i in range(points)]


def ticker_summaries(session: Session) -> list[TickerSummary]:
    stats = {
        ticker: (first, last, count, source)
        for ticker, first, last, count, source in session.execute(
            select(
                Price.ticker,
                func.min(Price.session_date),
                func.max(Price.session_date),
                func.count(),
                func.max(Price.source),
            ).group_by(Price.ticker)
        )
    }
    summaries = []
    for code, issuer in ISSUERS.items():
        first, last, count, source = stats.get(code, (None, None, 0, None))
        closes = list(
            session.scalars(
                select(Price.close).where(Price.ticker == code).order_by(Price.session_date)
            )
        )
        summaries.append(
            TickerSummary(
                code=code,
                name=issuer.name,
                short_name=issuer.short_name,
                first_date=first,
                last_date=last,
                rows=count,
                source=source,
                last_close=closes[-1] if closes else None,
                prev_close=closes[-2] if len(closes) > 1 else None,
                sparkline=_downsample(closes, SPARKLINE_POINTS),
            )
        )
    return summaries


def market_history(
    session: Session, ticker: str, start: date | None = None, end: date | None = None
) -> list[Candle]:
    series = _load_series(session, ticker)
    bands = bollinger_bands([price.close for price in series])
    candles = []
    for price, band in zip(series, bands):
        if start is not None and price.session_date < start:
            continue
        if end is not None and price.session_date > end:
            continue
        candles.append(
            Candle(
                session_date=price.session_date,
                open=price.open,
                high=price.high,
                low=price.low,
                close=price.close,
                adj_close=price.adj_close,
                volume=price.volume,
                band=band,
            )
        )
    return candles


def previous_session(session: Session, ticker: str, session_date: date) -> date | None:
    return session.scalar(
        select(func.max(Price.session_date)).where(
            Price.ticker == ticker, Price.session_date < session_date
        )
    )


def has_session(session: Session, ticker: str, session_date: date) -> bool:
    return (
        session.scalar(
            select(func.count()).where(
                Price.ticker == ticker, Price.session_date == session_date
            )
        )
        > 0
    )
