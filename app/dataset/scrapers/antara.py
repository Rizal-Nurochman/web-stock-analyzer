import re

from app.dataset.scrapers.base import Portal

# ANTARA tidak menyediakan sitemap (404). Arsip ditelusuri lewat halaman tag.
# Tag ticker sudah tertarget. Tag nama umum (bri, bca, bni) juga dipakai untuk liga sepak
# bola, berita daerah, dan lain-lain, jadi judulnya tetap diprafilter.
GENERIC_TAGS = {"bank-mandiri", "bri", "bni", "bca"}
TAGS = ("bbri", "bmri", "bbca", "bbni", "bank-mandiri", "bni", "bri", "bca")
FEEDS = ("https://www.antaranews.com/rss/ekonomi-bursa.xml",
         "https://www.antaranews.com/rss/ekonomi-finansial.xml")


class Antara(Portal):
    key = "antara"
    name = "ANTARA News"
    homepage = "https://www.antaranews.com/"
    access_method = "Halaman tag ticker/nama bank /tag/{tag}/{n} + RSS bursa dan finansial"
    coverage_note = "Arsip lewat tag redaksi; artikel tanpa tag emiten hanya tertangkap lewat RSS terbaru."
    article_pattern = re.compile(r"^https://www\.antaranews\.com/berita/\d+/[^/?#]+$")
    extra_junk = re.compile(r"^(Pewarta|Editor|Copyright|Dilarang keras)", re.I)

    def category_from_url(self, url):
        return None

    def discover(self, ctx):
        for tag in TAGS:
            yield from self.listing(
                ctx, lambda p, t=tag: f"https://www.antaranews.com/tag/{t}" + (f"/{p}" if p > 1 else ""),
                via=f"tag-{tag}", prefilter=tag in GENERIC_TAGS)
        yield from self.rss(ctx, list(FEEDS))
