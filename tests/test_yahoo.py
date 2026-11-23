import asyncio
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import db
from app.market.importer import import_rows, read_csv
from app.market.models import Price, PriceSyncStatus
from app.market.service import market_history
from app.market.sync import PriceSyncer
from app.market.yahoo import YahooError, parse_chart
from app.web.main import create_app

WIB_OFFSET = 7 * 3600
AFTER_CLOSE = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)  # 19.00 WIB


def _ts(day: date) -> int:
    # Yahoo memberi stempel waktu pembukaan 09.00 WIB = 02.00 UTC
    return int(datetime(day.year, day.month, day.day, 2, tzinfo=timezone.utc).timestamp())


def make_payload(days, *, start_price=1000.0, holidays=(), bad=(), currency="IDR"):
    ts, o, h, l, c, v = [], [], [], [], [], []
    price = start_price
    for i, day in enumerate(days):
        ts.append(_ts(day))
        if day in holidays:
            o.append(price), h.append(price), l.append(price), c.append(price), v.append(0)
            continue
        close = price + (5 if i % 2 else -5)
        hi, lo = max(price, close) + 10, min(price, close) - 10
        if day in bad:
            hi = min(price, close) - 1  # High lebih rendah dari Open/Close
        o.append(price), h.append(hi), l.append(lo), c.append(close), v.append(1_000_000 + i)
        price = close
    return {
        "chart": {
            "result": [
                {
                    "meta": {"currency": currency, "gmtoffset": WIB_OFFSET},
                    "timestamp": ts,
                    "indicators": {
                        "quote": [{"open": o, "high": h, "low": l, "close": c, "volume": v}],
                        "adjclose": [{"adjclose": c}],
                    },
                }
            ],
            "error": None,
        }
    }


def weekdays(start: date, count: int):
    out, day = [], start
    while len(out) < count:
        if day.weekday() < 5:
            out.append(day)
        day += timedelta(days=1)
    return out


def test_parse_skips_holidays_and_corrects_ohlc():
    days = weekdays(date(2026, 10, 1), 30)
    payload = make_payload(days, holidays={days[3]}, bad={days[5]})
    history = parse_chart("BBCA", payload, now=AFTER_CLOSE)
    assert len(history.rows) == 29
    assert history.skipped_holidays == 1
    assert history.corrected_rows == 1
    fixed = next(r for r in history.rows if r.session_date == days[5])
    assert fixed.high >= max(fixed.open, fixed.close)
    assert history.rows[0].session_date == days[0]  # tanggal WIB, bukan UTC


def test_today_before_close_is_not_stored():
    today = date(2026, 11, 23)
    days = weekdays(date(2026, 10, 26), 20) + [today]
    during_session = datetime(2026, 11, 23, 4, 0, tzinfo=timezone.utc)  # 11.00 WIB
    history = parse_chart("BBCA", make_payload(days), now=during_session)
    assert history.skipped_provisional is True
    assert history.rows[-1].session_date < today
    after = parse_chart("BBCA", make_payload(days), now=AFTER_CLOSE)
    assert after.rows[-1].session_date == today


def test_rejects_error_and_wrong_currency():
    with pytest.raises(YahooError):
        parse_chart("BBCA", {"chart": {"result": None, "error": {"code": "Not Found", "description": "No data"}}})
    with pytest.raises(YahooError, match="Mata uang"):
        parse_chart("BBCA", make_payload(weekdays(date(2026, 1, 1), 5), currency="USD"), now=AFTER_CLOSE)


def _client(payloads, status=None):
    def handler(request: httpx.Request) -> httpx.Response:
        symbol = request.url.path.rsplit("/", 1)[-1]
        code = (status or {}).get(symbol, 200)
        if code != 200:
            return httpx.Response(code, text="err")
        return httpx.Response(200, json=payloads[symbol])

    return lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_sync_replaces_csv_series_and_failure_keeps_data(tmp_path, sample_csv):
    engine = db.configure(f"sqlite:///{tmp_path / 'p.db'}")
    db.Base.metadata.create_all(engine)
    try:
        factory = db.get_session_factory()
        with factory() as s:
            import_rows(s, read_csv(sample_csv))  # CSV sebagai seed
            s.commit()

        days = weekdays(date(2026, 8, 3), 60)
        payloads = {f"{t}.JK": make_payload(days) for t in ("BBCA", "BBRI", "BMRI", "BBNI")}
        syncer = PriceSyncer(factory, client_factory=_client(payloads), request_gap=0)
        results = asyncio.run(syncer.run_once())
        assert all(r.ok for r in results), results

        with factory() as s:
            assert s.scalar(select(func.count()).select_from(Price).where(Price.ticker == "BBCA")) == 60
            assert set(s.scalars(select(Price.source))) == {"yahoo"}, "seri tidak boleh campur CSV dan Yahoo"
            assert len(market_history(s, "BBCA")) == 60

        # BBRI gagal (429) dan BMRI mengirim data terlalu sedikit: data tersimpan tetap utuh.
        payloads["BMRI.JK"] = make_payload(days[:10])
        failing = PriceSyncer(
            factory, client_factory=_client(payloads, {"BBRI.JK": 429}), request_gap=0
        )
        results = {r.ticker: r for r in asyncio.run(failing.run_once())}
        assert results["BBCA"].ok
        assert "429" in results["BBRI"].error
        assert "dipertahankan" in results["BMRI"].error
        with factory() as s:
            for code in ("BBRI", "BMRI"):
                assert s.scalar(select(func.count()).select_from(Price).where(Price.ticker == code)) == 60
                status = s.get(PriceSyncStatus, code)
                assert status.status == "error" and status.last_success_at is not None
    finally:
        engine.dispose()


def test_prices_status_endpoint(session):
    with TestClient(create_app()) as client:
        body = client.get("/api/prices/status").json()
    assert body["source"] == "yahoo"
    assert [t["ticker"] for t in body["tickers"]] == ["BBCA", "BBRI", "BMRI", "BBNI"]
    assert all(t["status"] == "pending" for t in body["tickers"])
