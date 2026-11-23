"""Validasi dan impor CSV harga gabungan ke tabel prices.

Pemakaian:
    python -m app.market.importer [path/ke/BBCA_BBRI_BMRI_BBNI_combined.csv]
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import DEFAULT_CSV
from app.market.models import Price
from app.market.tickers import ISSUERS, normalize_ticker

# Nama kolom dinormalisasi: huruf kecil, spasi dan tanda hubung menjadi garis bawah.
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "date": ("date", "tanggal", "datetime"),
    "ticker": ("ticker", "symbol", "kode", "emiten", "code"),
    "open": ("open",),
    "high": ("high",),
    "low": ("low",),
    "close": ("close",),
    "adj_close": ("adj_close", "adjclose", "adjusted_close"),
    "volume": ("volume", "vol"),
}
REQUIRED_COLUMNS = ("date", "ticker", "open", "high", "low", "close", "volume")
MAX_REPORTED_ERRORS = 25


@dataclass(frozen=True)
class PriceRow:
    ticker: str
    session_date: date
    open: float
    high: float
    low: float
    close: float
    adj_close: float | None
    volume: int


class CsvValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        shown = errors[:MAX_REPORTED_ERRORS]
        more = len(errors) - len(shown)
        message = "\n".join(shown)
        if more > 0:
            message += f"\n... dan {more} kesalahan lain"
        super().__init__(message)


@dataclass
class ImportResult:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    per_ticker: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return self.inserted + self.updated + self.unchanged


def _normalize_header(name: str) -> str:
    return name.strip().lower().replace(" ", "_").replace("-", "_").lstrip("﻿")


def _map_columns(fieldnames: list[str]) -> dict[str, str]:
    normalized = {_normalize_header(name): name for name in fieldnames}
    mapping: dict[str, str] = {}
    for target, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapping[target] = normalized[alias]
                break
    return mapping


def _parse_date(raw: str) -> date:
    value = raw.strip()
    # "2016-10-10", "2016-10-10 00:00:00+07:00", "2016-10-10T00:00:00"
    if len(value) >= 10 and value[4] == "-" and value[7] == "-":
        return date.fromisoformat(value[:10])
    for pattern in ("%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    raise ValueError(f"format tanggal tidak dikenal: {raw!r}")


def _parse_number(raw: str, column: str) -> float:
    value = raw.strip()
    if value == "":
        raise ValueError(f"{column} kosong")
    number = float(value)
    if number != number:  # NaN
        raise ValueError(f"{column} bukan angka")
    return number


def read_csv(path: Path) -> list[PriceRow]:
    """Baca dan validasi seluruh file. Semua kesalahan dikumpulkan sebelum gagal."""
    errors: list[str] = []
    rows: list[PriceRow] = []
    seen: set[tuple[str, date]] = set()

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise CsvValidationError(["File CSV kosong atau tanpa header."])
        mapping = _map_columns(list(reader.fieldnames))
        missing = [col for col in REQUIRED_COLUMNS if col not in mapping]
        if missing:
            raise CsvValidationError(
                [f"Kolom wajib tidak ditemukan: {', '.join(missing)}. Header: {reader.fieldnames}"]
            )

        for line_number, record in enumerate(reader, start=2):
            try:
                ticker = normalize_ticker(record[mapping["ticker"]] or "")
                if ticker not in ISSUERS:
                    raise ValueError(f"emiten tidak dikenal: {ticker!r}")
                session_date = _parse_date(record[mapping["date"]] or "")
                open_ = _parse_number(record[mapping["open"]] or "", "Open")
                high = _parse_number(record[mapping["high"]] or "", "High")
                low = _parse_number(record[mapping["low"]] or "", "Low")
                close = _parse_number(record[mapping["close"]] or "", "Close")
                adj_raw = (record.get(mapping["adj_close"]) or "").strip() if "adj_close" in mapping else ""
                adj_close = _parse_number(adj_raw, "Adj Close") if adj_raw else None
                volume_value = _parse_number(record[mapping["volume"]] or "", "Volume")
            except (ValueError, TypeError, KeyError) as exc:
                errors.append(f"Baris {line_number}: {exc}")
                continue

            if min(open_, high, low, close) < 0 or volume_value < 0:
                errors.append(f"Baris {line_number}: nilai negatif")
                continue
            if not (low <= min(open_, close) and max(open_, close) <= high):
                errors.append(
                    f"Baris {line_number}: rentang OHLC tidak valid (O={open_}, H={high}, L={low}, C={close})"
                )
                continue
            if volume_value != int(volume_value):
                errors.append(f"Baris {line_number}: volume bukan bilangan bulat")
                continue
            key = (ticker, session_date)
            if key in seen:
                errors.append(f"Baris {line_number}: duplikat {ticker} {session_date.isoformat()}")
                continue
            seen.add(key)
            rows.append(
                PriceRow(ticker, session_date, open_, high, low, close, adj_close, int(volume_value))
            )

    if errors:
        raise CsvValidationError(errors)
    if not rows:
        raise CsvValidationError(["CSV tidak berisi baris data."])
    return rows


def _same(existing: Price, row: PriceRow, source: str) -> bool:
    return (
        existing.source == source
        and existing.open == row.open
        and existing.high == row.high
        and existing.low == row.low
        and existing.close == row.close
        and existing.adj_close == row.adj_close
        and existing.volume == row.volume
    )


def import_rows(session: Session, rows: list[PriceRow], source: str = "csv") -> ImportResult:
    """Tulis baris secara idempoten. Pemanggil mengatur transaksi (satu commit)."""
    result = ImportResult()
    by_ticker: dict[str, list[PriceRow]] = defaultdict(list)
    for row in rows:
        by_ticker[row.ticker].append(row)

    for ticker, ticker_rows in by_ticker.items():
        existing = {
            price.session_date: price
            for price in session.scalars(select(Price).where(Price.ticker == ticker))
        }
        for row in ticker_rows:
            current = existing.get(row.session_date)
            if current is None:
                session.add(
                    Price(
                        ticker=row.ticker,
                        session_date=row.session_date,
                        open=row.open,
                        high=row.high,
                        low=row.low,
                        close=row.close,
                        adj_close=row.adj_close,
                        volume=row.volume,
                        source=source,
                    )
                )
                result.inserted += 1
            elif _same(current, row, source):
                result.unchanged += 1
            else:
                current.open = row.open
                current.high = row.high
                current.low = row.low
                current.close = row.close
                current.adj_close = row.adj_close
                current.volume = row.volume
                current.source = source
                result.updated += 1
        result.per_ticker[ticker] = len(ticker_rows)
    session.flush()
    return result


def import_csv(path: Path) -> ImportResult:
    from app.db import session_scope

    rows = read_csv(path)
    with session_scope() as session:
        return import_rows(session, rows)


def summarize(rows: list[PriceRow]) -> list[str]:
    counts = Counter(row.ticker for row in rows)
    lines = []
    for ticker in sorted(counts):
        dates = [row.session_date for row in rows if row.ticker == ticker]
        lines.append(f"  {ticker}: {counts[ticker]} baris, {min(dates)} s.d. {max(dates)}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Impor CSV harga gabungan ke PostgreSQL.")
    parser.add_argument("csv_path", nargs="?", default=str(DEFAULT_CSV))
    args = parser.parse_args(argv)

    path = Path(args.csv_path)
    if not path.exists():
        print(f"File tidak ditemukan: {path}", file=sys.stderr)
        return 1
    try:
        rows = read_csv(path)
    except CsvValidationError as exc:
        print(f"Validasi CSV gagal, tidak ada data yang ditulis:\n{exc}", file=sys.stderr)
        return 1

    from app.db import session_scope

    with session_scope() as session:
        result = import_rows(session, rows)

    print(f"Impor selesai: {result.total} baris dari {path.name}")
    print(f"  baru {result.inserted}, diperbarui {result.updated}, tidak berubah {result.unchanged}")
    print("\n".join(summarize(rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
