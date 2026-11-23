import re

from app.dataset.scrapers.base import Portal


class KompasMoney(Portal):
    key = "kompas_money"
    name = "Kompas Money"
    homepage = "https://money.kompas.com/"
    access_method = "Indeks per tanggal indeks.kompas.com (site=money) + artikel ?page=all"
    article_pattern = re.compile(r"^https://money\.kompas\.com/read/\d{4}/\d{2}/\d{2}/\d+/[^/?#]+$")
    extra_junk = re.compile(r"^(Dengarkan berita|Gabung KOMPAS|Simak breaking news|Baca berita tanpa iklan|"
                            r"Ikuti berita|Halaman:|Lihat Foto|Penulis\b|Editor\b)", re.I)

    def fetch_url(self, url):
        # Artikel multi-halaman digabung lewat ?page=all (tidak dilarang robots.txt).
        return url + "?page=all"

    def category_from_url(self, url):
        return "money"

    def discover(self, ctx):
        yield from self.date_index(
            ctx,
            lambda d, p: f"https://indeks.kompas.com/?site=money&date={d:%Y-%m-%d}"
                         + (f"&page={p}" if p > 1 else ""),
            via="indeks")
