import re

from app.dataset.scrapers.wordpress import WordPressPortal


class Infobank(WordPressPortal):
    key = "infobank"
    name = "Infobank"
    homepage = "https://infobanknews.com/"
    access_method = "Sitemap WordPress post-sitemapN.xml + halaman artikel"
    sitemap_index = "https://infobanknews.com/sitemap.xml"
    article_pattern = re.compile(
        r"^https://infobanknews\.com/(?!tag/|category/|author/|page/|wp-|event)[a-z0-9-]+/?$")

    def category_from_url(self, url):
        return None
