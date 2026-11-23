import re
from datetime import date

from app.dataset.scrapers.base import Portal

# Sitemap kuartalan tersedia sejak q1-2024 (awal arsip situs).
FIRST_YEAR = 2024


def _quarter(d: date) -> tuple[int, int]:
    return d.year, (d.month - 1) // 3 + 1


class KabarBursa(Portal):
    key = "kabarbursa"
    name = "KabarBursa"
    homepage = "https://www.kabarbursa.com/"
    access_method = "Sitemap kuartalan /sitemap/index/qN-YYYY.xml + halaman artikel"
    coverage_note = "Arsip situs dimulai 2024; tidak ada artikel 2023."
    article_pattern = re.compile(
        r"^https://www\.kabarbursa\.com/(?!sitemap|kategori|author|tag|profil-perusahaan)[a-z0-9-]+/[a-z0-9-]+$")

    def discover(self, ctx):
        sy, sq = _quarter(ctx.start)
        ey, eq = _quarter(ctx.end)
        sy = max(sy, FIRST_YEAR)
        if sy == FIRST_YEAR and ctx.start.year < FIRST_YEAR:
            sq = 1
        urls = []
        y, q = sy, sq
        while (y, q) <= (ey, eq):
            urls.append(f"https://www.kabarbursa.com/sitemap/index/q{q}-{y}.xml")
            y, q = (y + 1, 1) if q == 4 else (y, q + 1)
        current = "q{1}-{0}".format(*_quarter(date.today()))
        yield from self.sitemap(ctx, urls, via="sitemap-kuartal", final=lambda u: current not in u)
