from __future__ import annotations

from datetime import date
from typing import Iterator

from fastapi import HTTPException, Request

from app.db import get_session_factory
from app.market.tickers import ISSUERS, normalize_ticker


def get_session() -> Iterator:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def valid_ticker(ticker: str) -> str:
    code = normalize_ticker(ticker)
    if code not in ISSUERS:
        raise HTTPException(status_code=404, detail=f"Emiten {ticker!r} tidak dikenal")
    return code


def check_range(start: date | None, end: date | None) -> None:
    if start is not None and end is not None and start > end:
        raise HTTPException(
            status_code=422, detail="Tanggal awal harus sebelum atau sama dengan tanggal akhir"
        )


def get_syncer(request: Request):
    return request.app.state.syncer


def get_price_syncer(request: Request):
    return request.app.state.price_syncer
