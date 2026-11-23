import re
from urllib.parse import urlsplit

from app.dataset.scrapers.base import Portal

KANAL = ("investasi", "keuangan")


class Kontan(Portal):
    key = "kontan"
    name = "Kontan"
    homepage = "https://www.kontan.co.id/"
    access_method = "Indeks per tanggal kanal investasi dan keuangan (offset per_page) + halaman artikel"
    article_pattern = re.compile(r"^https://(investasi|keuangan)\.kontan\.co\.id/news/[^/?#]+$")
    extra_junk = re.compile(r"^(Cek Berita dan Artikel|Selanjutnya:|Reporter:|Editor:)", re.I)

    def category_from_url(self, url):
        return (urlsplit(url).hostname or "").split(".")[0] or None

    def discover(self, ctx):
        for kanal in KANAL:
            yield from self.date_index(
                ctx,
                lambda d, p, k=kanal: (
                    f"https://www.kontan.co.id/search/indeks?kanal={k}&tanggal={d:%d}&bulan={d:%m}"
                    f"&tahun={d:%Y}&pos=indeks" + (f"&per_page={(p - 1) * 20}" if p > 1 else "")),
                via=f"indeks-{kanal}",
            )
