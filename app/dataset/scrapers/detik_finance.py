import re

from app.dataset.scrapers.base import Portal


class DetikFinance(Portal):
    key = "detik_finance"
    name = "Detik Finance"
    homepage = "https://finance.detik.com/"
    access_method = "Indeks per tanggal finance.detik.com/indeks + artikel ?single=1"
    article_pattern = re.compile(
        r"^https://finance\.detik\.com/(?!foto|video|detiktv|infografis|sosok)[a-z-]+/d-\d+/[^/?#]+$")
    extra_junk = re.compile(r"^(ADVERTISEMENT|SCROLL TO CONTINUE|Simak juga Video|\(\w+/\w+\)$)", re.I)

    def fetch_url(self, url):
        # Artikel bersambung ditampilkan utuh dengan ?single=1.
        return url + "?single=1"

    def discover(self, ctx):
        yield from self.date_index(
            ctx, lambda d, p: f"https://finance.detik.com/indeks?page={p}&date={d:%m/%d/%Y}",
            via="indeks")
