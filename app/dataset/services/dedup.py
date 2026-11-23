"""Deteksi duplikasi dan sindikasi.

1. URL kanonis (di repository: seen_urls dan kolom unik articles.canonical_url).
2. Hash isi ternormalisasi: isi identik.
3. Judul ternormalisasi + kemiripan isi (shingle 5 kata) dalam jendela waktu: sindikasi.

Artikel duplikat tetap disimpan dengan sumbernya masing-masing, lalu diberi
duplicate_group_id yang sama agar pola penyebaran tetap bisa dianalisis.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from difflib import SequenceMatcher

from app.dataset.models.schema import Article

_NON_WORD = re.compile(r"[^0-9a-z]+")
TITLE_PREFIX = re.compile(r"^(video|foto|infografis|breaking news|live|update)\s*[:|-]\s*", re.IGNORECASE)
_DIGITS = re.compile(r"\d+")
WINDOW = timedelta(days=3)
TITLE_SIMILARITY = 0.85
CONTENT_SIMILARITY = 0.6


def normalize_text(text: str) -> str:
    return " ".join(_NON_WORD.sub(" ", text.lower()).split())


def content_hash(content: str) -> str:
    return hashlib.sha256(normalize_text(content).encode("utf-8")).hexdigest()


def title_key(title: str) -> str:
    return normalize_text(TITLE_PREFIX.sub("", title.strip()))


def shingles(text: str, size: int = 5) -> set[int]:
    words = normalize_text(text).split()
    if len(words) < size:
        return {int(hashlib.md5(" ".join(words).encode()).hexdigest()[:12], 16)}
    return {
        int(hashlib.md5(" ".join(words[i : i + size]).encode()).hexdigest()[:12], 16)
        for i in range(len(words) - size + 1)
    }


def jaccard(a: set[int], b: set[int]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass
class DuplicateMatch:
    group_id: str
    reason: str  # identical_content | syndicated
    other_article_id: str


def find_duplicate(content: str, title: str, published: datetime | None,
                   same_hash: Article | None, neighbours: list[Article]) -> DuplicateMatch | None:
    if same_hash is not None:
        return DuplicateMatch(same_hash.duplicate_group_id or same_hash.article_id,
                              "identical_content", same_hash.article_id)
    if published is None:
        return None
    key = title_key(title)
    numbers = set(_DIGITS.findall(key))
    mine = None
    for other in neighbours:
        title_ratio = SequenceMatcher(None, key, other.title_key).ratio()
        if title_ratio < TITLE_SIMILARITY:
            continue
        # Artikel bertemplat (kurs harian, IHSG hari ini) berbeda tanggal/angka di judul:
        # beritanya berbeda walau kalimatnya mirip.
        if numbers != set(_DIGITS.findall(other.title_key)):
            continue
        mine = mine or shingles(content)
        if jaccard(mine, shingles(other.content)) >= CONTENT_SIMILARITY:
            return DuplicateMatch(other.duplicate_group_id or other.article_id,
                                  "syndicated", other.article_id)
    return None


def window_bounds(published: datetime) -> tuple[str, str]:
    return (published - WINDOW).isoformat(), (published + WINDOW).isoformat()
