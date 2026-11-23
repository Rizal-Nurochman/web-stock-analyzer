import pytest
from fastapi.testclient import TestClient

from app.market.importer import import_rows, read_csv
from app.web.main import create_app


@pytest.fixture()
def client(session, sample_csv):
    import_rows(session, read_csv(sample_csv))
    session.commit()
    with TestClient(create_app()) as c:
        yield c


def test_tickers(client):
    data = client.get("/api/tickers").json()
    assert [t["code"] for t in data] == ["BBCA", "BBRI", "BMRI", "BBNI"]
    assert data[0]["last_date"] is not None


def test_market_range_inclusive_and_bands(client):
    body = client.get("/api/market/BBCA?start=2026-10-01&end=2026-10-02").json()
    assert [c["date"] for c in body["candles"]] == ["2026-10-01", "2026-10-02"]
    assert body["candles"][0]["bb_middle"] is not None
    full = client.get("/api/market/bbca.jk").json()
    assert full["candles"][0]["bb_upper"] is None
    assert len(full["candles"]) == 25


def test_market_errors(client):
    assert client.get("/api/market/BBTN").status_code == 404
    assert client.get("/api/market/BBCA?start=2026-10-05&end=2026-10-01").status_code == 422
    assert client.get("/api/market/BBCA?start=bukan-tanggal").status_code == 422
    empty = client.get("/api/market/BBCA?start=2030-01-01").json()
    assert empty["candles"] == []


def test_news_and_feeds(client):
    latest = client.get("/api/news/BBCA").json()
    assert latest["mode"] == "latest" and latest["status"] == "unavailable"
    session = client.get("/api/news/BBCA?session_date=2026-10-01").json()
    assert session["mode"] == "session" and session["window"] is not None
    assert client.get("/api/news/BBCA?session_date=2026-10-04").status_code == 404  # hari Minggu
    feeds = client.get("/api/feeds/status").json()
    assert [f["id"] for f in feeds["feeds"]] == [
        "cnbcindonesia", "kontan", "katadata", "kompas_money", "detik_finance", "cnnindonesia", "infobank"]
    assert all(f["status"] == "pending" for f in feeds["feeds"])
    assert feeds["model"]["status"] == "disabled" and feeds["retention_days"] == 7
