import re

from app.dataset.scrapers.base import Portal

# Parameter tanggal di /indeks diabaikan situs, jadi arsip ditelusuri lewat halaman tag.
TAGS = ("bbri", "bmri", "bbca", "bbni", "bank-bri", "bank-mandiri", "bank-bca", "bank-bni")


class InvestorDaily(Portal):
    key = "investor"
    name = "Investor Daily"
    homepage = "https://investor.id/"
    access_method = "Halaman tag ticker/nama bank /tag/{tag}/{n} + halaman artikel"
    coverage_note = ("Hanya artikel yang diberi tag ticker atau nama bank oleh redaksi; "
                     "indeks per tanggal tidak mendukung tanggal lampau.")
    article_pattern = re.compile(r"^https://investor\.id/[a-z-]+/\d+/[^/?#]+$")

    def discover(self, ctx):
        for tag in TAGS:
            yield from self.listing(
                ctx, lambda p, t=tag: f"https://investor.id/tag/{t}" + (f"/{p}" if p > 1 else ""),
                via=f"tag-{tag}")
