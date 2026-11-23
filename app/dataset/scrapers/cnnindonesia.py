import re

from app.dataset.scrapers.base import Portal


class CNNIndonesia(Portal):
    key = "cnnindonesia"
    name = "CNN Indonesia (Ekonomi)"
    homepage = "https://www.cnnindonesia.com/ekonomi"
    access_method = "Indeks per tanggal kanal ekonomi /ekonomi/indeks/5 + halaman artikel"
    article_pattern = re.compile(r"^https://www\.cnnindonesia\.com/ekonomi/\d{14}-\d+-\d+/[^/?#]+$")
    extra_junk = re.compile(r"^(\[Gambas|ADVERTISEMENT|SCROLL TO CONTINUE)", re.I)

    def category_from_url(self, url):
        return "ekonomi"

    def discover(self, ctx):
        yield from self.date_index(
            ctx,
            lambda d, p: f"https://www.cnnindonesia.com/ekonomi/indeks/5?date={d:%Y/%m/%d}"
                         + (f"&page={p}" if p > 1 else ""),
            via="indeks")
