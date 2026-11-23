from datetime import date

from app.market.importer import import_rows, read_csv
from app.market.service import market_history, ticker_summaries


def _load(session, sample_csv):
    import_rows(session, read_csv(sample_csv))
    session.commit()


def test_band_values_stay_the_same_when_range_changes(session, sample_csv):
    _load(session, sample_csv)
    full = {c.session_date: c.band for c in market_history(session, "BBCA")}
    narrow = market_history(session, "BBCA", start=date(2026, 10, 1), end=date(2026, 10, 5))
    assert narrow, "rentang harus berisi candle"
    for candle in narrow:
        assert candle.band == full[candle.session_date]
        assert candle.band is not None  # jendela dihitung dari seri penuh, bukan dari filter


def test_first_19_sessions_have_no_band(session, sample_csv):
    _load(session, sample_csv)
    candles = market_history(session, "BBNI")
    assert len(candles) == 20
    assert all(c.band is None for c in candles[:19])
    assert candles[19].band is not None


def test_summaries_cover_all_four_banks(session, sample_csv):
    _load(session, sample_csv)
    summaries = {s.code: s for s in ticker_summaries(session)}
    assert set(summaries) == {"BBCA", "BBRI", "BMRI", "BBNI"}
    assert summaries["BBCA"].rows == 25
    assert summaries["BBCA"].sparkline
