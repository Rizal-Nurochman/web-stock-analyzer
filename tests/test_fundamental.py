import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.fundamental.metrics import compute
from app.fundamental.service import FundamentalService
from datetime import date

from app.fundamental.yahoo import parse_dividends, parse_summary, parse_timeseries
from app.market.yahoo import YahooError
from app.web.main import create_app
from tests.conftest import FIXTURES

RAW = json.loads((FIXTURES / "yahoo_fundamental_bbca.json").read_text())


TODAY = date(2026, 11, 23)


def _inputs():
    return {
        "series": parse_timeseries(RAW["timeseries"]),
        "summary": parse_summary(RAW["summary"]),
        "dividends": parse_dividends(RAW["chart"]),
        "today": TODAY,
    }


def _items(result):
    return {i["key"]: i for s in result["sections"] for i in s["items"]}


def test_compute_matches_yahoo_reported_ratios():
    result = compute(**_inputs())
    items = _items(result)
    assert result["quarter_end"] == "2026-09-30" and result["quarter_label"] == "Q3 2026"
    # Yahoo sendiri melaporkan PE TTM 11,75, PBV 2,46, BVPS 2.307,19, market cap 697,32 T.
    assert items["pe_ttm"]["value"] == pytest.approx(11.75, abs=0.01)
    assert items["pbv"]["value"] == pytest.approx(2.46, abs=0.01)
    assert items["bvps"]["value"] == pytest.approx(2307.19, abs=0.01)
    assert items["market_cap"]["value"] == pytest.approx(697.32e12, rel=1e-3)
    # Annualised = laba Q1-Q3 2026 x 4/3 dibagi saham beredar.
    assert items["eps_annualised"]["value"] == pytest.approx(45_215_827e6 * 4 / 3 / 122_876_240_600, rel=1e-6)
    # Ex date Des 2025 (55), Mar 2026 (281), Jun 2026 (20), Sep 2026 (25).
    assert items["dividend_ttm"]["value"] == pytest.approx(381)
    assert items["payout_ratio"]["value"] == pytest.approx(381 / 483 * 100)
    assert items["next_ex_date"]["value"] == "2026-11-30" and items["next_dividend"]["value"] == 35
    assert result["dividend_history"][0]["amount"] == 25
    assert items["free_float"]["value"] == pytest.approx(39.56, abs=0.01)


def test_missing_comparison_quarter_is_not_guessed():
    result = compute(**_inputs())
    growth = {row["key"]: row for row in result["growth"]}
    # Yahoo tidak memberi laba Q3 2025, jadi YoY kuartal dan YTD dibiarkan kosong.
    assert growth["net_income"]["quarter_yoy"] is None
    assert growth["net_income"]["ytd_yoy"] is None
    assert growth["net_income"]["annual_yoy"] == pytest.approx((57_537_287 / 54_836_305 - 1) * 100)
    labels = [c["label"] for c in result["periods"]["columns"]]
    assert labels[-3:] == ["Annualised 2026", "TTM", "FY 2025"]


def test_dividend_ttm_ignores_yahoo_zero_when_history_exists():
    inputs = _inputs()
    inputs["summary"]["summaryDetail"]["trailingAnnualDividendRate"] = 0.0
    items = _items(compute(**inputs))
    assert items["dividend_ttm"]["value"] == pytest.approx(381)
    inputs["dividends"] = []
    assert _items(compute(**inputs))["dividend_ttm"]["value"] is None


def test_quarter_yoy_when_comparison_exists():
    inputs = _inputs()
    inputs["series"]["quarterlyNetIncomeCommonStockholders"].insert(1, ("2025-09-30", 14_000_000e6))
    growth = {row["key"]: row for row in compute(**inputs)["growth"]}
    assert growth["net_income"]["quarter_yoy"] == pytest.approx((15_681_381 / 14_000_000 - 1) * 100)


def test_negative_cash_flow_has_no_multiple():
    inputs = _inputs()
    inputs["series"]["trailingOperatingCashFlow"][-1] = ("2026-09-30", -1e12)
    items = _items(compute(**inputs))
    assert items["pcf_ttm"]["value"] is None
    assert "negatif" in items["pcf_ttm"]["hint"]


def test_summary_error_raises():
    with pytest.raises(YahooError):
        parse_summary({"quoteSummary": {"result": None, "error": {"code": "Not Found", "description": "No data"}}})


class FakeClient:
    def __init__(self):
        self.calls = 0
        self.fail = False

    async def fetch(self, ticker):
        self.calls += 1
        if self.fail:
            raise YahooError("Yahoo membatasi permintaan (HTTP 429). Coba lagi nanti")
        inputs = _inputs()
        inputs.pop("today")
        return inputs

    async def aclose(self):
        pass


def test_service_caches_and_serves_stale_on_error():
    async def scenario():
        client = FakeClient()
        service = FundamentalService(client, ttl_seconds=3600)
        first = await service.get("BBCA")
        await service.get("BBCA")
        assert first["status"] == "ok" and client.calls == 1
        client.fail = True
        stale = await service.get("BBCA", refresh=True)
        assert stale["status"] == "stale" and "429" in stale["error"] and stale["sections"]
        missing = await service.get("BBRI")
        assert missing["status"] == "unavailable" and "sections" not in missing

    asyncio.run(scenario())


def test_endpoint(session):
    app = create_app()
    app.state.fundamentals = FundamentalService(FakeClient())
    with TestClient(app) as client:
        body = client.get("/api/fundamentals/bbca").json()
        assert body["ticker"] == "BBCA" and body["status"] == "ok"
        assert [s["id"] for s in body["sections"]][:2] == ["valuation", "per_share"]
        assert client.get("/api/fundamentals/BBTN").status_code == 404
