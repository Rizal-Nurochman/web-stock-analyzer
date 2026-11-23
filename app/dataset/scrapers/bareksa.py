import re

from app.dataset.scrapers.base import Portal

CATEGORIES = ("saham", "bareksa-insight", "reksa-dana")


class Bareksa(Portal):
    key = "bareksa"
    name = "Bareksa"
    homepage = "https://www.bareksa.com/"
    access_method = "Sitemap berita per kategori (saham, bareksa-insight, reksa-dana) + halaman artikel"
    coverage_note = ("Hanya sekitar 50 artikel terakhir per kategori (±1 bulan). Daftar arsip "
                     "dirender JavaScript dan tidak tersedia sebagai HTML.")
    article_pattern = re.compile(r"^https://www\.bareksa\.com/berita/[a-z-]+/\d{4}-\d{2}-\d{2}/[^/?#]+$")

    def discover(self, ctx):
        urls = [f"https://www.bareksa.com/sitemap/berita/{c}/news.xml" for c in CATEGORIES]
        # Sitemap bergulir: jangan ditandai selesai agar run berikutnya menangkap artikel baru.
        yield from self.sitemap(ctx, urls, via="sitemap-kategori", lastmod_is_publish=True,
                                final=lambda u: False)

    def category_from_url(self, url):
        parts = url.split("/")
        return parts[4] if len(parts) > 4 else None
