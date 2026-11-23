"""Konfigurasi aplikasi yang dibaca dari variabel lingkungan."""

from __future__ import annotations

import os
from datetime import time, timedelta, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"
DEFAULT_CSV = ROOT_DIR / "data" / "BBCA_BBRI_BMRI_BBNI_combined.csv"

DEFAULT_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/web_stock_analyzer"

# WIB tidak memakai daylight saving, jadi offset tetap cukup dan tidak butuh tzdata di Windows.
WIB = timezone(timedelta(hours=7), name="WIB")

# Penutupan perdagangan reguler BEI. Dipakai untuk batas jendela berita per sesi.
IDX_SESSION_CLOSE = time(16, 0)


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def news_sync_enabled() -> bool:
    return _flag("NEWS_SYNC_ENABLED", True)


def news_sync_interval_seconds() -> int:
    """Jeda antarputaran pemantauan news sitemap (default 5 menit)."""
    return max(60, int(os.environ.get("NEWS_SYNC_INTERVAL_SECONDS", "300")))


def news_retention_days() -> int:
    """Berapa lama artikel disimpan di memori proses. Tidak ada yang ditulis ke database."""
    return max(1, int(os.environ.get("NEWS_RETENTION_DAYS", "7")))


def sentiment_enabled() -> bool:
    return _flag("SENTIMENT_ENABLED", True)


def sentiment_model_id() -> str:
    return os.environ.get("SENTIMENT_MODEL", "intanm/indonesian_financial_sentiment_analysis")


def price_sync_enabled() -> bool:
    """Ambil histori harian dari Yahoo Finance saat startup lalu berkala."""
    return _flag("PRICE_SYNC_ENABLED", True)


def price_sync_interval_seconds() -> int:
    return max(300, int(os.environ.get("PRICE_SYNC_INTERVAL_SECONDS", "3600")))
