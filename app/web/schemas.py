from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

Sentiment = Literal["positif", "netral", "negatif", "belum_dinilai"]


class TickerOut(BaseModel):
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


class CandleOut(BaseModel):
    date: date
    open: float
    high: float
    low: float
    close: float
    adj_close: float | None
    volume: int
    bb_upper: float | None
    bb_middle: float | None
    bb_lower: float | None


class MarketOut(BaseModel):
    ticker: str
    start: date | None
    end: date | None
    first_date: date | None
    last_date: date | None
    candles: list[CandleOut]


class ArticleOut(BaseModel):
    id: str
    title: str
    url: str
    publisher: str
    published_at: datetime
    sentiment: Sentiment
    confidence: float | None


class CoverageOut(BaseModel):
    earliest_article_at: datetime | None
    observed_since: datetime | None


class WindowOut(BaseModel):
    start: datetime
    end: datetime
    previous_session: date | None


class SentimentSummaryOut(BaseModel):
    positif: int
    netral: int
    negatif: int
    belum_dinilai: int


class NewsOut(BaseModel):
    ticker: str
    mode: Literal["latest", "session"]
    session_date: date | None
    status: Literal["ok", "empty", "partial", "unavailable"]
    reason: str | None
    window: WindowOut | None
    coverage: CoverageOut
    articles: list[ArticleOut]
    summary: SentimentSummaryOut | None


class FeedOut(BaseModel):
    id: str
    name: str
    publisher: str
    url: str
    status: Literal["ok", "error", "pending"]
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    first_observed_at: datetime | None
    last_error: str | None
    last_item_count: int | None
    last_new_count: int | None


class ModelOut(BaseModel):
    id: str
    status: Literal["pending", "loading", "ready", "error", "disabled"]
    error: str | None


class FeedsOut(BaseModel):
    syncing: bool
    auto_sync: bool
    interval_seconds: int
    retention_days: int
    last_run_finished_at: datetime | None
    next_run_at: datetime | None
    model: ModelOut
    feeds: list[FeedOut]


class PriceStatusOut(BaseModel):
    ticker: str
    status: Literal["ok", "error", "pending"]
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None
    last_session_date: date | None
    rows: int | None
    new_rows: int | None
    skipped_holidays: int | None
    corrected_rows: int | None


class PricesSyncOut(BaseModel):
    source: Literal["yahoo"]
    syncing: bool
    auto_sync: bool
    interval_seconds: int
    last_run_finished_at: datetime | None
    next_run_at: datetime | None
    tickers: list[PriceStatusOut]
