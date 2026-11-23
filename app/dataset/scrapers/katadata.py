import re
from datetime import date

from app.dataset.scrapers.base import Portal, month_starts


class Katadata(Portal):
    key = "katadata"
    name = "Katadata"
    homepage = "https://katadata.co.id/"
    access_method = "Sitemap bulanan /sitemap/post/YYYY-MM.xml + halaman artikel"
    article_pattern = re.compile(r"^https://katadata\.co\.id/[a-z0-9-]+/[a-z0-9-]+/[0-9a-f]{12,14}/[^/?#]+$")

    def discover(self, ctx):
        today = date.today()
        months = [m for m in month_starts(ctx.start, ctx.end)]
        urls = [f"https://katadata.co.id/sitemap/post/{m:%Y-%m}.xml" for m in months]
        # Sitemap bulan berjalan masih bertambah, jadi tidak ditandai selesai.
        current = f"{today:%Y-%m}"
        yield from self.sitemap(ctx, urls, via="sitemap-bulanan", lastmod_is_publish=True,
                                final=lambda u: current not in u)

    def category_from_url(self, url):
        parts = url.split("/")
        return "/".join(parts[3:5]) if len(parts) > 5 else None
