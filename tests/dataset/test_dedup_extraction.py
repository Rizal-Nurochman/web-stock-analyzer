from datetime import datetime

import pytest

from app.config import WIB
from app.dataset.models.schema import Article
from app.dataset.services import dedup
from app.dataset.services.extraction import (
    NoContent,
    Paywalled,
    clean_content,
    extract_article,
    parse_datetime,
)

BODY = (
    "Jakarta - PT Bank Central Asia Tbk (BBCA) membukukan laba bersih Rp41 triliun pada sembilan "
    "bulan pertama. Pertumbuhan kredit didorong segmen korporasi dan konsumer. "
) * 4


def test_content_hash_ignores_whitespace_and_case():
    assert dedup.content_hash("Laba  BCA naik.") == dedup.content_hash("laba bca naik")


def test_syndicated_article_is_grouped():
    other = Article(article_id="a-1", title="Laba BCA Naik 12 Persen", content=BODY,
                    title_key=dedup.title_key("Laba BCA Naik 12 Persen"), duplicate_group_id=None)
    match = dedup.find_duplicate(BODY + " Sumber: ANTARA.", "Laba BCA naik 12 persen!",
                                 datetime(2026, 11, 23, tzinfo=WIB), None, [other])
    assert match and match.reason == "syndicated" and match.group_id == "a-1"


def test_different_articles_are_not_grouped():
    other = Article(article_id="a-1", title="Laba BCA Naik 12 Persen", content=BODY,
                    title_key=dedup.title_key("Laba BCA Naik 12 Persen"))
    assert dedup.find_duplicate("Isi lain sama sekali tentang IHSG dan rupiah. " * 10,
                                "IHSG Ditutup Melemah", datetime(2026, 11, 23, tzinfo=WIB),
                                None, [other]) is None


def test_parse_datetime_normalizes_to_wib():
    assert parse_datetime("2023-03-15T11:01:43Z").isoformat() == "2023-03-15T18:01:43+07:00"
    assert parse_datetime("2023/03/15 18:01:43").isoformat() == "2023-03-15T18:01:43+07:00"
    assert parse_datetime("Wed, 15 Mar 2023 18:01:43 +0700").hour == 18


def test_clean_content_drops_site_furniture_and_credit_suffix():
    raw = "Paragraf satu berita.\nBaca juga: Saham lain naik\nADVERTISEMENT\nParagraf dua. (fik/hns)\nEditor: Budi"
    assert clean_content(raw) == "Paragraf satu berita.\nParagraf dua."


def _page(body: str, extra_head: str = "") -> str:
    return f"""<html lang="id"><head><title>Judul</title>
    <meta property="article:published_time" content="2023-03-15T18:01:43+07:00">
    <meta name="author" content="Budi Santoso">
    <link rel="canonical" href="https://www.example.co.id/berita/1/judul">{extra_head}</head>
    <body><nav>Menu Home Ekonomi Bisnis</nav><article><h1>Judul Berita</h1>{body}</article>
    <footer>Copyright 2026 Example</footer></body></html>"""


def test_extract_article_reads_metadata_and_body():
    paragraphs = "".join(f"<p>{BODY} Kalimat ke-{i} yang berbeda.</p>" for i in range(3))
    art = extract_article(_page(paragraphs), "https://www.example.co.id/berita/1/judul?utm_source=x")
    assert art.published_at.isoformat() == "2023-03-15T18:01:43+07:00"
    assert art.author == "Budi Santoso"
    assert art.language == "id"
    assert "Menu Home" not in art.content and "Copyright" not in art.content
    assert art.canonical_url == "https://example.co.id/berita/1/judul"


def test_short_or_paywalled_pages_are_rejected():
    with pytest.raises(NoContent):
        extract_article(_page("<p>Video singkat.</p>"), "https://www.example.co.id/x")
    with pytest.raises(Paywalled):
        extract_article(_page("<p>Ringkasan.</p><div>Berlangganan untuk membaca artikel ini</div>"),
                        "https://www.example.co.id/y")
    ld = '<script type="application/ld+json">{"@type":"NewsArticle","isAccessibleForFree":false}</script>'
    with pytest.raises(Paywalled):
        extract_article(_page(f"<p>{BODY}</p>", ld), "https://www.example.co.id/z")


def test_clean_content_strips_widgets_credits_but_keeps_tickers():
    raw = ("Saham bank besar menguat (BBRI/BBCA)\n"
           "Penutup berita. (Mentari Puspadini/ayh) [Gambas:Video CNBC]\n"
           "Artikel ini telah masuk Arsip. Berlangganan untuk membacanya kembali kapan saja.")
    assert clean_content(raw) == "Saham bank besar menguat (BBRI/BBCA)\nPenutup berita."


def test_templated_daily_articles_with_different_dates_are_not_syndication():
    t1, t2 = "Kurs Dolar AS di BCA Hari Ini, Jumat 6 November 2026", "Kurs Dolar AS di BCA Hari Ini, Senin 9 November 2026"
    other = Article(article_id="a-1", title=t1, content=BODY, title_key=dedup.title_key(t1))
    assert dedup.find_duplicate(BODY, t2, datetime(2026, 11, 9, tzinfo=WIB), None, [other]) is None
