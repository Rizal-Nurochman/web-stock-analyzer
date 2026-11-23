import re

from app.dataset.scrapers.base import Portal


class IDXChannel(Portal):
    key = "idxchannel"
    name = "IDX Channel"
    homepage = "https://www.idxchannel.com/"
    access_method = "Indeks per tanggal (halaman pertama) + sitemap kanal market-news dan banking"
    coverage_note = ("Indeks hanya menampilkan ±16 artikel pertama per hari; halaman berikutnya "
                     "dimuat JavaScript. Sitemap kanal hanya memuat artikel terbaru.")
    article_pattern = re.compile(
        r"^https://www\.idxchannel\.com/(market-news|banking|economics|news)/[a-z0-9-]+$")

    def discover(self, ctx):
        yield from self.date_index(
            ctx, lambda d, p: f"https://www.idxchannel.com/indeks?date={d:%Y-%m-%d}",
            paginate=False, via="indeks")
        yield from self.sitemap(
            ctx, ["https://www.idxchannel.com/market-news/sitemap.xml",
                  "https://www.idxchannel.com/banking/sitemap.xml"],
            via="sitemap-kanal", lastmod_is_publish=True, final=lambda u: False)
