import pytest
from sqlalchemy import func, select

from app.market.importer import CsvValidationError, import_rows, read_csv
from app.market.models import Price


def test_reads_all_rows_per_ticker(sample_csv):
    rows = read_csv(sample_csv)
    counts = {}
    for row in rows:
        counts[row.ticker] = counts.get(row.ticker, 0) + 1
    assert counts == {"BBCA": 25, "BBRI": 22, "BMRI": 21, "BBNI": 20}


def test_reimport_keeps_row_count(session, sample_csv):
    rows = read_csv(sample_csv)
    first = import_rows(session, rows)
    session.commit()
    second = import_rows(session, rows)
    session.commit()
    assert first.inserted == 88
    assert second.inserted == 0 and second.unchanged == 88
    assert session.scalar(select(func.count()).select_from(Price)) == 88


def _write(tmp_path, body):
    path = tmp_path / "x.csv"
    path.write_text("Date,Ticker,Open,High,Low,Close,Adj Close,Volume\n" + body)
    return path


def test_rejects_duplicates_and_bad_ohlc(tmp_path):
    path = _write(
        tmp_path,
        "2020-01-02,BBCA,100,110,90,105,105,10\n"
        "2020-01-02,BBCA,100,110,90,105,105,10\n"
        "2020-01-03,BBCA,100,99,90,95,95,10\n",
    )
    with pytest.raises(CsvValidationError) as exc:
        read_csv(path)
    joined = "\n".join(exc.value.errors)
    assert "duplikat" in joined
    assert "rentang OHLC" in joined


def test_rejects_unknown_ticker_and_missing_column(tmp_path):
    with pytest.raises(CsvValidationError, match="tidak dikenal"):
        read_csv(_write(tmp_path, "2020-01-02,BBTN,1,1,1,1,1,1\n"))
    bad = tmp_path / "y.csv"
    bad.write_text("Date,Open,High,Low,Close,Volume\n2020-01-02,1,1,1,1,1\n")
    with pytest.raises(CsvValidationError, match="ticker"):
        read_csv(bad)
