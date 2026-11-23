import re

from app.dataset.scrapers.base import Portal

# Tag ticker sudah tertarget. Tag nama umum (bri, bca, bni) juga dipakai untuk liga sepak
# bola, berita daerah, dan lain-lain, jadi judulnya tetap diprafilter.
GENERIC_TAGS = {"bank-mandiri", "bri", "bni", "bca"}
TAGS = ("bbri", "bmri", "bbca", "bbni", "bank-mandiri", "bri", "bni", "bca")
PAGE_SIZE = 15  # pagination memakai offset kelipatan 15


class Republika(Portal):
    key = "republika"
    name = "Republika"
    homepage = "https://www.republika.co.id/"
    access_method = "Halaman tag ticker/nama bank /tag/{tag}/{offset} + halaman artikel"
    coverage_note = "Hanya artikel yang diberi tag ticker atau nama bank oleh redaksi."
    article_pattern = re.compile(r"^https://[a-z]+\.republika\.co\.id/berita/[a-z0-9]+/[^/?#]+$")

    def category_from_url(self, url):
        return url.split("//", 1)[1].split(".", 1)[0]

    def discover(self, ctx):
        for tag in TAGS:
            yield from self.listing(
                ctx,
                lambda p, t=tag: f"https://republika.co.id/tag/{t}" + (f"/{(p - 1) * PAGE_SIZE}" if p > 1 else ""),
                via=f"tag-{tag}", prefilter=tag in GENERIC_TAGS)
