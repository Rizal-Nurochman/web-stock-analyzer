"""Tujuh portal yang dapat diakses penuh, dipantau lewat news sitemap.

News sitemap (format Google News) diperbarui dalam hitungan menit setelah artikel terbit
dan memuat judul, sehingga satu putaran pemantauan cukup beberapa permintaan per portal.
Pola URL artikel, cara unduh, dan pembersih teks dipakai ulang dari adapter dataset.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.dataset.scrapers import get_portal
from app.dataset.scrapers.base import Portal


@dataclass(frozen=True)
class LiveSource:
    key: str
    sitemaps: tuple[str, ...]

    @property
    def portal(self) -> Portal:
        return get_portal(self.key)


LIVE_SOURCES: tuple[LiveSource, ...] = (
    LiveSource("cnbcindonesia", (
        "https://www.cnbcindonesia.com/market/sitemap_news.xml",
        "https://www.cnbcindonesia.com/news/sitemap_news.xml",
        "https://www.cnbcindonesia.com/research/sitemap_news.xml",
    )),
    LiveSource("kontan", (
        "https://keuangan.kontan.co.id/news/sitemap.xml",
        "https://investasi.kontan.co.id/news/sitemap.xml",
    )),
    LiveSource("katadata", (
        "https://katadata.co.id/sitemap/finansial/sitemap_news.xml",
        "https://katadata.co.id/sitemap/berita/sitemap_news.xml",
    )),
    LiveSource("kompas_money", ("https://money.kompas.com/sitemap-news-money.xml",)),
    LiveSource("detik_finance", ("https://finance.detik.com/sitemap_news.xml",)),
    LiveSource("cnnindonesia", ("https://www.cnnindonesia.com/ekonomi/sitemap_news.xml",)),
    LiveSource("infobank", ("https://infobanknews.com/news-sitemap.xml",)),
)

SOURCES_BY_KEY = {source.key: source for source in LIVE_SOURCES}
