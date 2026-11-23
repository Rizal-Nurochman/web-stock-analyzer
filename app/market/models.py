from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Price(Base):
    __tablename__ = "prices"

    ticker: Mapped[str] = mapped_column(String(8), primary_key=True)
    session_date: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    adj_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # "yahoo" atau "csv". Satu emiten tidak dicampur: sinkronisasi Yahoo mengganti seluruh seri.
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="csv")


class PriceSyncStatus(Base):
    __tablename__ = "price_sync_status"

    ticker: Mapped[str] = mapped_column(String(8), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    last_session_date: Mapped[date | None] = mapped_column(Date)
    rows: Mapped[int | None] = mapped_column(Integer)
    new_rows: Mapped[int | None] = mapped_column(Integer)
    skipped_holidays: Mapped[int | None] = mapped_column(Integer)
    corrected_rows: Mapped[int | None] = mapped_column(Integer)
