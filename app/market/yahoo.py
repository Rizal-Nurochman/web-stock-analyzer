"""Histori harian dari endpoint chart Yahoo Finance (simbol BEI berakhiran .JK).

Endpoint ini tidak resmi dan tanpa jaminan layanan, jadi hasilnya selalu disimpan ke
database. Dashboard hanya membaca data tersimpan dan tetap jalan ketika Yahoo tidak
bisa dihubungi.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import httpx

from app.config import IDX_SESSION_CLOSE, WIB
from app.market.importer import PriceRow

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
# Yahoo menolak klien tanpa User-Agent peramban dengan HTTP 403/429.
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
TIMEOUT = 25.0
# Beri jeda setelah penutupan sebelum candle hari ini dianggap final.
FINAL_AFTER = timedelta(minutes=15)


class YahooError(Exception):
    pass


@dataclass
class YahooHistory:
    rows: list[PriceRow]
    skipped_holidays: int
    corrected_rows: int
    skipped_provisional: bool


def symbol_for(ticker: str) -> str:
    return f"{ticker}.JK"


def session_is_final(day: date, now: datetime) -> bool:
    close_at = datetime.combine(day, IDX_SESSION_CLOSE, tzinfo=WIB) + FINAL_AFTER
    return now >= close_at


def parse_chart(ticker: str, payload: dict, now: datetime | None = None) -> YahooHistory:
    now = now or datetime.now(timezone.utc)
    chart = payload.get("chart") or {}
    if chart.get("error"):
        error = chart["error"]
        raise YahooError(f"Yahoo menolak permintaan: {error.get('description') or error.get('code')}")
    results = chart.get("result") or []
    if not results:
        raise YahooError("Respons Yahoo tidak berisi data")

    result = results[0]
    meta = result.get("meta") or {}
    if meta.get("currency") not in (None, "IDR"):
        raise YahooError(f"Mata uang tak terduga: {meta.get('currency')}")
    offset = timedelta(seconds=meta.get("gmtoffset", 7 * 3600))
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    adj = ((result.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose")

    rows: list[PriceRow] = []
    holidays = corrected = 0
    provisional = False
    seen: set[date] = set()
    for i, ts in enumerate(timestamps):
        o, h, l, c, v = (quote.get(k, [None] * len(timestamps))[i] for k in ("open", "high", "low", "close", "volume"))
        if None in (o, h, l, c):
            continue
        day = (datetime.fromtimestamp(ts, timezone.utc) + offset).date()
        if day in seen:
            continue
        volume = int(v or 0)
        # Yahoo mengisi hari libur bursa dengan candle datar bervolume 0. Itu bukan sesi.
        if volume == 0 and o == h == l == c:
            holidays += 1
            continue
        if not session_is_final(day, now):
            provisional = True
            continue
        high, low = max(h, o, c), min(l, o, c)
        if (high, low) != (h, l):
            corrected += 1
        seen.add(day)
        rows.append(
            PriceRow(
                ticker=ticker,
                session_date=day,
                open=float(o),
                high=float(high),
                low=float(low),
                close=float(c),
                adj_close=float(adj[i]) if adj and adj[i] is not None else None,
                volume=volume,
            )
        )
    if not rows:
        raise YahooError("Respons Yahoo tidak berisi sesi final")
    return YahooHistory(rows, holidays, corrected, provisional)


async def fetch_history(client: httpx.AsyncClient, ticker: str) -> YahooHistory:
    response = await client.get(
        CHART_URL.format(symbol=symbol_for(ticker)),
        params={
            "period1": 0,
            "period2": int(datetime.now(timezone.utc).timestamp()) + 86400,
            "interval": "1d",
            "includeAdjustedClose": "true",
        },
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=TIMEOUT,
        follow_redirects=True,
    )
    if response.status_code == 429:
        raise YahooError("Yahoo membatasi permintaan (HTTP 429). Coba lagi nanti")
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError as exc:
        raise YahooError("Respons Yahoo bukan JSON") from exc
    return parse_chart(ticker, payload)
