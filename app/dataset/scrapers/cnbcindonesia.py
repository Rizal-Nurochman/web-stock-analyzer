import re

from app.dataset.scrapers.base import Portal

# ID kanal indeks diverifikasi 23 Nov 2026: market=5, news=3, research=127.
CHANNELS = {"market": 5, "news": 3, "research": 127}


class CNBCIndonesia(Portal):
    key = "cnbcindonesia"
    name = "CNBC Indonesia"
    homepage = "https://www.cnbcindonesia.com/"
    access_method = "Indeks per tanggal (market, news, research) + halaman artikel"
    article_pattern = re.compile(
        r"^https://www\.cnbcindonesia\.com/(market|news|research)/\d{14}-\d+-\d+/[^/?#]+$")
    extra_junk = re.compile(r"^(\[Gambas|Next Article|Artikel Selanjutnya|Saksikan video)", re.I)

    def discover(self, ctx):
        for channel, cid in CHANNELS.items():
            yield from self.date_index(
                ctx,
                lambda d, p, ch=channel, i=cid: (
                    f"https://www.cnbcindonesia.com/{ch}/indeks/{i}?date={d:%Y/%m/%d}"
                    + (f"&page={p}" if p > 1 else "")),
                via=f"indeks-{channel}",
            )
