import re

from app.dataset.scrapers.wordpress import WordPressPortal


class Finansialku(WordPressPortal):
    key = "finansialku"
    name = "Finansialku"
    homepage = "https://www.finansialku.com/"
    access_method = "Sitemap WordPress post-sitemapN.xml + halaman artikel (Crawl-delay 10 detik dipatuhi)"
    coverage_note = "Sebagian besar konten edukasi keuangan pribadi; artikel tentang emiten jarang."
    sitemap_index = "https://www.finansialku.com/sitemap_index.xml"
    # URL artikel memakai segmen kategori: /berita/<slug>/, /perencana-keuangan/<slug>/.
    article_pattern = re.compile(
        r"^https://www\.finansialku\.com/(?!tag/|category/|author/|page/|wp-)[a-z0-9-]+(/[a-z0-9-]+)?/?$")

    def category_from_url(self, url):
        parts = [p for p in url.split("/")[3:] if p]
        return parts[0] if len(parts) > 1 else None
