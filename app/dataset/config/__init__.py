"""Pemuatan konfigurasi: settings.toml lalu ditimpa argumen CLI."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path

from app.config import ROOT_DIR

DEFAULT_SETTINGS = Path(__file__).with_name("settings.toml")


@dataclass(frozen=True)
class Settings:
    start: date
    end: date
    database: Path
    exports_dir: Path
    logs_dir: Path
    user_agent: str
    min_interval: float
    timeout: float
    max_retries: int
    max_consecutive_blocks: int
    min_content_chars: int
    enabled_sources: tuple[str, ...]
    parallel_sources: int
    # Batas untuk uji cepat. None berarti tanpa batas.
    max_articles_per_source: int | None = None
    max_units_per_source: int | None = None
    extra: dict = field(default_factory=dict)

    def with_overrides(self, **kwargs) -> "Settings":
        return replace(self, **{k: v for k, v in kwargs.items() if v is not None})


def _path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT_DIR / path


def load_settings(path: Path | None = None) -> Settings:
    with open(path or DEFAULT_SETTINGS, "rb") as handle:
        raw = tomllib.load(handle)
    period, storage, http = raw["period"], raw["storage"], raw["http"]
    settings = Settings(
        start=date.fromisoformat(period["start"]),
        end=date.fromisoformat(period["end"]),
        database=_path(storage["database"]),
        exports_dir=_path(storage["exports_dir"]),
        logs_dir=_path(storage["logs_dir"]),
        user_agent=http["user_agent"],
        min_interval=float(http["min_interval_seconds"]),
        timeout=float(http["timeout_seconds"]),
        max_retries=int(http["max_retries"]),
        max_consecutive_blocks=int(http["max_consecutive_blocks"]),
        min_content_chars=int(raw["extraction"]["min_content_chars"]),
        enabled_sources=tuple(raw["sources"]["enabled"]),
        parallel_sources=int(raw["sources"].get("parallel_sources", 4)),
    )
    if settings.start > settings.end:
        raise ValueError("period.start harus sebelum atau sama dengan period.end")
    return settings
