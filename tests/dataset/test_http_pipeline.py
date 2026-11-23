import re
from datetime import date

import httpx
import pytest

from app.dataset.config import load_settings
from app.dataset.database.session import Database
from app.dataset.models.schema import Article, ArticleStock, SeenUrl
from app.dataset.models.types import Candidate
from app.dataset.scrapers.base import Portal
from app.dataset.services.http import Blocked, PoliteClient, RobotsDisallowed, site_key
from app.dataset.services.pipeline import Collector, SourceStats

UA = "TestBot/1.0"
PARA = ("PT Bank Rakyat Indonesia (Persero) Tbk atau BBRI mencatat laba bersih Rp45 triliun. "
        "Kinerja kredit mikro dan pertumbuhan aset menopang saham BBRI di bursa. ")


def article_html(title, published="2023-01-10T10:00:00+07:00", body=PARA * 5):
    return (f'<html lang="id"><head><title>{title}</title>'
            f'<meta property="article:published_time" content="{published}"></head>'
            f"<body><article><h1>{title}</h1><p>{body}</p><p>{body}</p></article></body></html>")


def make_client(routes, calls=None):
    def handler(request):
        if calls is not None:
            calls.append(str(request.url))
        for pattern, response in routes.items():
            if re.search(pattern, str(request.url)):
                return response() if callable(response) else response
        return httpx.Response(404)

    return PoliteClient(UA, min_interval=0, transport=httpx.MockTransport(handler), sleep=lambda s: None)


def test_site_key_groups_subdomains():
    assert site_key("investasi.kontan.co.id") == site_key("www.kontan.co.id") == "kontan.co.id"
    assert site_key("finance.detik.com") == "detik.com"


def test_robots_and_block_detection():
    client = make_client({
        r"robots\.txt": httpx.Response(200, text="User-agent: *\nDisallow: /search/\n"),
        r"/search/": httpx.Response(200, text="x"),
        r"/cf": httpx.Response(403, text="<title>Just a moment...</title> cf-chl"),
        r"/ok": httpx.Response(200, text="ok"),
    })
    with pytest.raises(RobotsDisallowed):
        client.get("https://site.test/search/bbri")
    with pytest.raises(Blocked, match="Cloudflare"):
        client.get("https://site.test/cf")
    assert client.get("https://site.test/ok").text == "ok"


def test_retry_on_server_error_then_success():
    responses = iter([httpx.Response(503), httpx.Response(200, text="ok")])
    client = make_client({r"robots": httpx.Response(404), r"/flaky": lambda: next(responses)})
    assert client.get("https://site.test/flaky").text == "ok"


class FakePortal(Portal):
    key = "fake"
    name = "Fake News"
    homepage = "https://fake.test/"
    article_pattern = re.compile(r"fake\.test/berita/")

    def __init__(self, candidates):
        self.candidates = candidates

    def discover(self, ctx):
        yield from self.candidates


@pytest.fixture()
def collector(tmp_path):
    settings = load_settings().with_overrides(start=date(2023, 1, 1), end=date(2023, 12, 31),
                                              database=tmp_path / "t.db")
    routes = {
        r"robots": httpx.Response(404),
        r"/berita/1$": httpx.Response(200, text=article_html("Laba BBRI Tumbuh 12 Persen")),
        r"/berita/2$": httpx.Response(200, text=article_html("Laba BBRI Tumbuh 12 Persen!")),
        r"/berita/3$": httpx.Response(200, text=article_html("Laba BBRI Lama", "2022-05-01T10:00:00+07:00")),
        r"/berita/4$": httpx.Response(200, text=article_html(
            "Harga Cabai Naik Jelang Lebaran", body="Harga cabai di pasar naik tajam minggu ini. " * 20)),
        r"/berita/5$": httpx.Response(500),
    }
    db = Database(tmp_path / "t.db")
    return Collector(settings, db, make_client(routes)), db


def test_pipeline_saves_dedupes_filters_and_resumes(collector):
    col, db = collector
    portal = FakePortal([])
    stats = SourceStats("fake")
    for i, title in [(1, "Laba BBRI"), (2, "Laba BBRI"), (3, "Laba BBRI lama"),
                     (4, "Laba BBRI hoax"), (5, "BBRI error")]:
        col.process(portal, Candidate(f"https://fake.test/berita/{i}", title, None, "test"), stats)
    # Kandidat yang judulnya tidak lolos prafilter tidak diunduh.
    col.process(portal, Candidate("https://fake.test/berita/9", "Harga Cabai Naik", None, "test"), stats)

    assert stats.saved_relevant == 2
    assert stats.duplicates == 1           # /2 identik dengan /1, disimpan dan ditandai
    assert stats.out_of_range == 1         # /3 terbit 2022
    assert stats.irrelevant == 1           # /4 isinya bukan tentang emiten
    assert stats.failed == 1               # /5 HTTP 500 setelah retry
    assert stats.prefiltered_out == 1

    with db.read() as s:
        rows = s.query(Article).order_by(Article.article_id).all()
        assert len(rows) == 2
        assert rows[0].duplicate_group_id == rows[1].duplicate_group_id is not None
        pairs = s.query(ArticleStock).all()
        assert {p.stock_code for p in pairs} == {"BBRI"}
        assert all(p.predicted_sentiment is None and p.sentiment_model is None for p in pairs)
        assert s.get(SeenUrl, "https://fake.test/berita/5").status == "failed"

    # Resume: URL yang sudah tuntas tidak diunduh ulang.
    again = SourceStats("fake")
    col.process(portal, Candidate("https://fake.test/berita/1", "Laba BBRI", None, "test"), again)
    assert again.already_seen == 1 and again.fetched == 0
