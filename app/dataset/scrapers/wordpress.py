"""Portal WordPress (Infobank, Finansialku): post-sitemapN.xml memuat seluruh artikel."""

import re

from app.dataset.scrapers.base import Portal


class WordPressPortal(Portal):
    sitemap_index = ""
    post_sitemap = re.compile(r"/post-sitemap\d*\.xml$")

    def discover(self, ctx):
        # lastmod di indeks = waktu artikel terbaru di sub-sitemap itu. Sub-sitemap yang
        # lastmod-nya sebelum awal periode pasti hanya berisi artikel lama: tidak perlu diunduh.
        entries = self.sitemap_entries(ctx, self.sitemap_index)
        children = [loc for loc, when, _ in entries
                    if self.post_sitemap.search(loc) and (when is None or when >= ctx.start)]

        def number(url):
            m = re.search(r"post-sitemap(\d*)\.xml", url)
            return int(m.group(1) or 1)

        children.sort(key=number)
        newest = children[-1] if children else None
        # Sitemap terakhir masih terisi artikel baru, jadi tidak ditandai selesai.
        yield from self.sitemap(ctx, children, via="sitemap-post", final=lambda u: u != newest)
