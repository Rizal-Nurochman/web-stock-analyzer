"""Pengambil data fundamental mentah dari tiga endpoint Yahoo Finance.

- fundamentals-timeseries: laporan keuangan (kuartalan, tahunan, trailing/TTM). Tanpa crumb.
- chart (events=div): riwayat dividen per ex date. Field trailingAnnualDividendRate di
  quoteSummary kadang 0 walau dividen sudah dibagikan (mis. BBNI), jadi dividen TTM dihitung
  dari riwayat ini.
- quoteSummary: harga terkini, saham beredar, free float, dividen, forward EPS. Butuh cookie
  dan crumb yang diambil sekali lalu dipakai ulang sampai ditolak.

Laporan keuangan sengaja diambil dari timeseries saja. Modul financialData di quoteSummary
memakai definisi lain (mis. arus kas operasi bertanda berbeda), dan mencampur keduanya
membuat rasio tidak konsisten.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone

import httpx

from app.market.yahoo import CHART_URL, TIMEOUT, YahooError, symbol_for

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)
TIMESERIES_URL = "https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{symbol}"
SUMMARY_URL = "https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"
COOKIE_URL = "https://fc.yahoo.com"
CRUMB_URL = "https://query2.finance.yahoo.com/v1/test/getcrumb"

JSON = {"Accept": "application/json"}
SUMMARY_MODULES = "price,summaryDetail,defaultKeyStatistics,calendarEvents"

QUARTERLY = (
    "TotalRevenue",
    "NetIncomeCommonStockholders",
    "PretaxIncome",
    "NetInterestIncome",
    "TotalAssets",
    "TotalLiabilitiesNetMinorityInterest",
    "CommonStockEquity",
    "TotalEquityGrossMinorityInterest",
    "CashAndCashEquivalents",
    "OrdinarySharesNumber",
    "TotalDebt",
    "NetLoan",
    "AllowanceForLoansAndLeaseLosses",
    "TotalDeposits",
)
ANNUAL = ("TotalRevenue", "NetIncomeCommonStockholders", "DilutedEPS", "CashDividendsPaid")
TRAILING = (
    "TotalRevenue",
    "NetIncomeCommonStockholders",
    "DilutedEPS",
    "NetInterestIncome",
    "OperatingCashFlow",
    "InvestingCashFlow",
    "FinancingCashFlow",
    "CapitalExpenditure",
    "FreeCashFlow",
)
TYPES = (
    [f"quarterly{t}" for t in QUARTERLY]
    + [f"annual{t}" for t in ANNUAL]
    + [f"trailing{t}" for t in TRAILING]
)
# Jangkauan cukup panjang untuk histori tahunan; Yahoo tetap hanya memberi ~5 kuartal terakhir.
HISTORY_START = 1420070400  # 2015-01-01


def parse_timeseries(payload: dict) -> dict[str, list[tuple[str, float]]]:
    """{tipe: [(asOfDate ISO, nilai), ...]} terurut naik. Nilai kosong dibuang."""
    result = ((payload.get("timeseries") or {}).get("result")) or []
    series: dict[str, list[tuple[str, float]]] = {}
    for item in result:
        types = (item.get("meta") or {}).get("type") or []
        if not types:
            continue
        name = types[0]
        points = []
        for point in item.get(name) or []:
            if not point or point.get("asOfDate") is None:
                continue
            raw = (point.get("reportedValue") or {}).get("raw")
            if raw is None:
                continue
            points.append((point["asOfDate"], float(raw)))
        if points:
            series[name] = sorted(points)
    return series


WIB_OFFSET = timedelta(hours=7)


def parse_dividends(payload: dict) -> list[tuple[str, float]]:
    """[(ex date ISO WIB, nominal per saham), ...] terurut naik."""
    results = (payload.get("chart") or {}).get("result") or []
    if not results:
        return []
    events = ((results[0].get("events") or {}).get("dividends")) or {}
    out = []
    for event in events.values():
        when, amount = event.get("date"), event.get("amount")
        if when is None or amount is None:
            continue
        day = (datetime.fromtimestamp(int(when), timezone.utc) + WIB_OFFSET).date().isoformat()
        out.append((day, float(amount)))
    return sorted(out)


def parse_summary(payload: dict) -> dict:
    """Ratakan modul quoteSummary menjadi {modul: {kunci: nilai mentah}}."""
    body = payload.get("quoteSummary") or {}
    if body.get("error"):
        error = body["error"]
        raise YahooError(f"Yahoo menolak permintaan: {error.get('description') or error.get('code')}")
    results = body.get("result") or []
    if not results:
        raise YahooError("Respons quoteSummary kosong")
    flat: dict[str, dict] = {}
    for module, values in results[0].items():
        if not isinstance(values, dict):
            continue
        flat[module] = {}
        for key, value in values.items():
            if isinstance(value, dict):
                if "raw" in value:
                    flat[module][key] = value["raw"]
                elif not value:
                    flat[module][key] = None
                else:
                    flat[module][key] = value
            else:
                flat[module][key] = value
    return flat


class YahooFundamentalClient:
    """Satu klien HTTP bersama dengan crumb yang di-cache."""

    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client or httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
            follow_redirects=True,
        )
        self._crumb: str | None = None
        self._crumb_lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get_crumb(self, refresh: bool = False) -> str:
        async with self._crumb_lock:
            if self._crumb and not refresh:
                return self._crumb
            # fc.yahoo.com menjawab 404 tetapi tetap memasang cookie sesi yang dibutuhkan crumb.
            # Endpoint crumb menjawab 406 bila Accept dibatasi ke JSON, jadi header itu hanya
            # dipasang pada permintaan data.
            await self._client.get(COOKIE_URL)
            response = await self._client.get(CRUMB_URL)
            crumb = response.text.strip()
            if response.status_code != 200 or not crumb or "<" in crumb:
                raise YahooError(f"Gagal mengambil crumb Yahoo (HTTP {response.status_code})")
            self._crumb = crumb
            return crumb

    async def summary(self, ticker: str) -> dict:
        url = SUMMARY_URL.format(symbol=symbol_for(ticker))
        for attempt in range(2):
            crumb = await self._get_crumb(refresh=attempt > 0)
            response = await self._client.get(
                url, params={"modules": SUMMARY_MODULES, "crumb": crumb}, headers=JSON
            )
            if response.status_code in (401, 403) and attempt == 0:
                continue  # crumb kedaluwarsa: ambil baru sekali
            _raise_for(response)
            return parse_summary(response.json())
        raise YahooError("Yahoo menolak crumb")

    async def timeseries(self, ticker: str) -> dict[str, list[tuple[str, float]]]:
        response = await self._client.get(
            TIMESERIES_URL.format(symbol=symbol_for(ticker)),
            params={"type": ",".join(TYPES), "period1": HISTORY_START, "period2": int(time.time())},
            headers=JSON,
        )
        _raise_for(response)
        return parse_timeseries(response.json())

    async def dividends(self, ticker: str) -> list[tuple[str, float]]:
        response = await self._client.get(
            CHART_URL.format(symbol=symbol_for(ticker)),
            params={"range": "5y", "interval": "1mo", "events": "div"},
            headers=JSON,
        )
        _raise_for(response)
        return parse_dividends(response.json())

    async def fetch(self, ticker: str) -> dict:
        """Semua bahan mentah untuk metrics.compute, diambil paralel."""
        series, summary, dividends = await asyncio.gather(
            self.timeseries(ticker), self.summary(ticker), self.dividends(ticker)
        )
        return {"series": series, "summary": summary, "dividends": dividends}


def _raise_for(response: httpx.Response) -> None:
    if response.status_code == 429:
        raise YahooError("Yahoo membatasi permintaan (HTTP 429). Coba lagi nanti")
    if response.status_code >= 400:
        raise YahooError(f"Yahoo menjawab HTTP {response.status_code}")
