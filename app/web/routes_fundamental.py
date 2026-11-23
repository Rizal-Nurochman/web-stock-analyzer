from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app.fundamental.service import FundamentalService
from app.web.deps import valid_ticker

router = APIRouter(prefix="/api", tags=["fundamental"])


def get_fundamentals(request: Request) -> FundamentalService:
    return request.app.state.fundamentals


@router.get("/fundamentals/{ticker}")
async def fundamentals(
    ticker: str = Depends(valid_ticker),
    refresh: bool = Query(False, description="Abaikan cache dan ambil ulang dari Yahoo"),
    service: FundamentalService = Depends(get_fundamentals),
):
    """Metrik fundamental dari Yahoo Finance, di-cache di memori (tidak disimpan ke database)."""
    return await service.get(ticker, refresh=refresh)
