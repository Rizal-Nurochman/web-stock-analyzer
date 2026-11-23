import re

from app.dataset.scrapers.base import Portal

CHANNELS = ("bisnis", "saham")


class Liputan6(Portal):
    key = "liputan6"
    name = "Liputan6"
    homepage = "https://www.liputan6.com/"
    access_method = "Indeks per tanggal kanal bisnis dan saham (halaman pertama) + halaman artikel"
    coverage_note = ("robots.txt melarang parameter ?page=, jadi hanya ±20 artikel pertama per kanal "
                     "per hari yang dapat ditelusuri.")
    article_pattern = re.compile(r"^https://www\.liputan6\.com/(bisnis|saham)/read/\d+/[^/?#]+$")
    extra_junk = re.compile(r"^(Advertisement|Lanjutkan Membaca|Infografis|Video Pilihan|Saksikan)", re.I)

    def discover(self, ctx):
        for channel in CHANNELS:
            yield from self.date_index(
                ctx, lambda d, p, ch=channel: f"https://www.liputan6.com/{ch}/indeks/{d:%Y/%m/%d}",
                paginate=False, via=f"indeks-{channel}")
