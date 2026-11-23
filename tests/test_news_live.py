import asyncio
import re
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from app.dataset.services.http import PoliteClient
from app.market.importer import import_rows, read_csv
from app.news import service
from app.news.canonical import canonical_url
from app.news.live import LiveNewsService, parse_news_sitemap
from app.news.model import Prediction
from app.news.sources import LiveSource

NOW = datetime.now(timezone.utc)
PARA = ("PT Bank Rakyat Indonesia (Persero) Tbk atau BBRI mencatat laba bersih Rp45 triliun. "
        "Kinerja kredit dan pertumbuhan aset menopang saham BBRI di bursa. ")
BNI_PARA = "Sementara itu saham BBNI melemah tajam karena kredit macet meningkat dan laba turun. "


def sitemap(items):
    urls = "".join(
        f"<url><loc>{u}</loc><news:news><news:publication_date>{d.isoformat()}</news:publication_date>"
        f"<news:title><![CDATA[{t}]]></news:title></news:news></url>" for u, t, d in items)
    return f'<?xml version="1.0"?><urlset xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">{urls}</urlset>'


def article(title, body, published=NOW):
    return (f'<html lang="id"><head><title>{title}</title><meta property="article:published_time" '
            f'content="{published.isoformat()}"></head><body><article><h1>{title}</h1>'
            f"<p>{body}</p><p>{body}</p></article></body></html>")


class FakeModel:
    model_id = "fake-model"
    error = None

    def __init__(self, ready=True):
        self.status = "ready" if ready else "loading"
        self.calls = []

    @property
    def ready(self):
        return self.status == "ready"

    def predict(self, sentences):
        if not self.ready:
            return None
        self.calls.append(sentences)
        text = " ".join(sentences).lower()
        label = "negatif" if "melemah" in text or "turun" in text else "positif"
        return Prediction(label, 0.9, len(sentences))


CNBC = "https://www.cnbcindonesia.com/market/"


@pytest.fixture()
def routes():
    return {
        r"robots\.txt": httpx.Response(404),
        r"sitemap_news\.xml": httpx.Response(200, text=sitemap([
            (CNBC + "20261123100000-17-1/laba-bbri-naik", "Laba BBRI Naik, BBNI Tertekan", NOW),
            (CNBC + "20261123110000-17-2/harga-cabai", "Harga Cabai Naik Jelang Natal", NOW),
            (CNBC + "20261123120000-17-3/bank-bri-csr", "BRI Gelar Lomba Lari", NOW),
        ])),
        r"laba-bbri-naik": httpx.Response(200, text=article("Laba BBRI Naik, BBNI Tertekan", PARA * 3 + BNI_PARA * 3)),
        r"bank-bri-csr": httpx.Response(200, text=article("BRI Gelar Lomba Lari", "Ribuan pelari ikut lomba di Jakarta. " * 20)),
    }


def make_service(routes, model, calls=None):
    def handler(request):
        if calls is not None:
            calls.append(str(request.url))
        for pattern, response in routes.items():
            if re.search(pattern, str(request.url)):
                return response
        return httpx.Response(404)

    client = PoliteClient("TestBot", min_interval=0, transport=httpx.MockTransport(handler), sleep=lambda s: None)
    source = LiveSource("cnbcindonesia", ("https://www.cnbcindonesia.com/market/sitemap_news.xml",))
    return LiveNewsService(model, interval_seconds=300, retention_days=7, sources=(source,), client=client)


def test_parse_news_sitemap_reads_title_and_date():
    items = parse_news_sitemap(sitemap([("https://x.test/a", "Judul A", NOW)]))
    assert items[0].title == "Judul A" and items[0].published is not None


def test_poll_detects_relevant_articles_and_scores_each_bank_separately(routes):
    calls = []
    live = make_service(routes, FakeModel(), calls)
    asyncio.run(live.run_once())

    snap = live.snapshot()
    assert len(snap.articles) == 1, "artikel cabai (prafilter) dan CSR (tidak relevan) tidak masuk"
    stocks = snap.articles[0].stocks
    assert stocks["BBRI"].label == "positif" and stocks["BBNI"].label == "negatif"
    assert not any("harga-cabai" in c for c in calls), "judul tak relevan tidak diunduh"

    # Putaran kedua tidak mengunduh ulang artikel yang sudah diperiksa.
    calls.clear()
    asyncio.run(live.run_once())
    assert not any("laba-bbri" in c or "bank-bri-csr" in c for c in calls)
    assert live.source_states()[0].status == "ok"


def test_articles_wait_for_model_then_get_scored(routes):
    model = FakeModel(ready=False)
    live = make_service(routes, model)
    asyncio.run(live.run_once())
    bbri = live.snapshot().articles[0].stocks["BBRI"]
    assert bbri.label is None and bbri.sentences, "belum dinilai, kalimat target disimpan sementara"

    model.status = "ready"
    live.score_pending()  # dipanggil saat model selesai dimuat, tanpa menunggu putaran berikutnya
    bbri = live.snapshot().articles[0].stocks["BBRI"]
    assert bbri.label == "positif" and bbri.sentences == [], "teks dibuang setelah dinilai"


def test_sitemap_failure_marks_source_error_without_crashing(routes):
    routes[r"sitemap_news\.xml"] = httpx.Response(503)
    live = make_service(routes, FakeModel())
    asyncio.run(live.run_once())
    state = live.source_states()[0]
    assert state.status == "error" and "503" in state.last_error


def test_old_articles_are_pruned(routes):
    live = make_service(routes, FakeModel())
    asyncio.run(live.run_once())
    key = canonical_url(CNBC + "20261123100000-17-1/laba-bbri-naik")
    live._articles[key].published_at = NOW - timedelta(days=30)
    live._prune()
    assert live.snapshot().articles == []


def test_latest_news_view(routes):
    live = make_service(routes, FakeModel())
    assert service.latest_news(live, "BBRI").status == "unavailable"
    asyncio.run(live.run_once())
    result = service.latest_news(live, "BBNI")
    assert result.status == "ok" and result.articles[0].sentiment == "negatif"
    assert result.articles[0].confidence == 0.9
    assert service.latest_news(live, "BBCA").status == "empty"


def test_session_window_before_monitoring_is_unavailable(routes, session, sample_csv):
    import_rows(session, read_csv(sample_csv))
    session.commit()
    live = make_service(routes, FakeModel())
    asyncio.run(live.run_once())
    result = service.session_news(live, session, "BBCA", date(2026, 10, 1))
    assert result.status == "unavailable" and "memori" in result.reason


def test_summary_counts_all_articles_not_only_the_page(routes):
    live = make_service(routes, FakeModel())
    asyncio.run(live.run_once())
    result = service.latest_news(live, "BBNI", limit=1)
    assert result.summary == {"positif": 0, "netral": 0, "negatif": 1, "belum_dinilai": 0}
    assert service.latest_news(live, "BBCA").summary is None
