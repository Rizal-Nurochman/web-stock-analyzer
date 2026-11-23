"""Ekstraksi isi artikel yang bersih beserta metadata.

Isi diambil dengan Trafilatura (tanpa komentar dan tabel, mode presisi), lalu baris
sisa seperti "Baca juga", iklan, ajakan menonton video, dan kredit redaksi dibuang.
Metadata diambil dari JSON-LD lalu meta tag, karena keduanya memuat jam publikasi.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import trafilatura
from bs4 import BeautifulSoup

from app.config import WIB
from app.dataset.models.types import ExtractedArticle
from app.news.canonical import canonical_url


class NoContent(Exception):
    pass


class Paywalled(Exception):
    pass


# Baris pendek yang bukan bagian isi berita.
JUNK_LINE = re.compile(
    r"^\s*(?:"
    r"baca(?: juga| selengkapnya)?\s*:|lihat juga|simak juga|simak video|saksikan|tonton|"
    r"video(?: pilihan)?\s*:|\[gambas:|scroll to continue|advertisement|iklan\b|ads by|"
    r"halaman (?:selanjutnya|berikutnya)|berita terkait|artikel terkait|"
    r"ikuti (?:kami|berita|saluran|whatsapp|update)|follow (?:us|kami)|download aplikasi|"
    r"dapatkan update|klik di sini|cek berita|pilihan editor|terpopuler|"
    r"pewarta\s*:|editor\s*:|redaktur\s*:|reporter\s*:|penulis\s*:|sumber\s*:|foto\s*:|"
    r"copyright|hak cipta|©|disclaimer\s*:|"
    r"tag\s*:|tags\s*:|kata kunci\s*:|topik\s*:"
    r")",
    re.IGNORECASE,
)
# Kredit redaksi di ujung paragraf, mis. "(ant/ara)" atau "(fik/hns)".
# Kode redaksi selalu huruf kecil ("/ayh"), jadi "(BBRI/BBCA)" di ujung kalimat tidak terhapus.
CREDIT_SUFFIX = re.compile(r"\s*\((?:[A-Za-z][A-Za-z .']{1,40}/)+[a-z]{2,8}\)\s*$")
# Sisipan widget di tengah atau ujung baris, mis. "[Gambas:Video CNBC]".
INLINE_JUNK = re.compile(r"\s*\[Gambas:[^\]]*\]\s*", re.IGNORECASE)
TRAILING_NOTICE = re.compile(
    r"^(artikel ini telah masuk arsip|dapatkan berita|simak berita|baca berita dengan sedikit iklan)",
    re.IGNORECASE)
PAYWALL_MARKERS = (
    "berlangganan untuk membaca", "khusus pelanggan", "konten premium", "artikel premium",
    "silakan login untuk membaca", "untuk membaca artikel ini", "langganan sekarang",
    "baca selengkapnya hanya untuk", "akses penuh",
)
ID_STOPWORDS = {"yang", "dan", "di", "dengan", "untuk", "dari", "ini", "itu", "pada", "dalam",
                "tidak", "akan", "juga", "ke", "oleh", "sebagai", "adalah", "karena", "tersebut"}

DATE_META_NAMES = (
    "article:published_time", "og:published_time", "publishdate", "pubdate", "publish-date",
    "dtk:publishdate", "content_publisheddate", "content_PublishedDate", "datepublished",
    "date", "dc.date", "dc.date.issued", "sailthru.date", "parsely-pub-date",
)
AUTHOR_META_NAMES = ("author", "dtk:author", "content_author", "article:author", "parsely-author")


def parse_datetime(value: str | None) -> datetime | None:
    """Kembalikan datetime ber-zona Asia/Jakarta. Waktu tanpa zona dianggap WIB."""
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    parsed: datetime | None = None
    iso = text.replace("Z", "+00:00").replace("/", "-")
    iso = re.sub(r"^(\d{4}-\d{2}-\d{2})\s+", r"\1T", iso)
    try:
        parsed = datetime.fromisoformat(iso)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(text)
        except (TypeError, ValueError, IndexError):
            match = re.search(r"(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?", iso)
            if not match:
                return None
            y, m, d, hh, mm, ss = match.groups()
            parsed = datetime(int(y), int(m), int(d), int(hh or 0), int(mm or 0), int(ss or 0))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=WIB)
    return parsed.astimezone(WIB)


def _json_ld(soup: BeautifulSoup) -> list[dict]:
    items: list[dict] = []
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text() or ""
        try:
            data = json.loads(raw.strip())
        except (ValueError, TypeError):
            # Beberapa portal menaruh karakter kontrol mentah di JSON-LD.
            try:
                data = json.loads(re.sub(r"[\x00-\x1f]", " ", raw.strip()))
            except (ValueError, TypeError):
                continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                if "@graph" in item and isinstance(item["@graph"], list):
                    stack.extend(item["@graph"])
                items.append(item)
            elif isinstance(item, list):
                stack.extend(item)
    return items


def _article_ld(items: list[dict]) -> dict:
    for item in items:
        kind = item.get("@type")
        kinds = kind if isinstance(kind, list) else [kind]
        if any(k in ("NewsArticle", "Article", "ReportageNewsArticle", "BlogPosting", "AnalysisNewsArticle")
               for k in kinds):
            return item
    return {}


def _ld_author(value) -> str | None:
    if not value:
        return None
    values = value if isinstance(value, list) else [value]
    names = []
    for entry in values:
        name = entry.get("name") if isinstance(entry, dict) else entry
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return ", ".join(dict.fromkeys(names)) or None


def _meta(soup: BeautifulSoup, names: tuple[str, ...]) -> str | None:
    lowered = {n.lower() for n in names}
    for tag in soup.find_all("meta"):
        key = (tag.get("property") or tag.get("name") or tag.get("itemprop") or "").lower()
        if key in lowered and tag.get("content"):
            return tag["content"].strip()
    return None


def clean_content(text: str, extra_junk: re.Pattern[str] | None = None) -> str:
    lines = []
    for raw in text.splitlines():
        line = CREDIT_SUFFIX.sub("", INLINE_JUNK.sub(" ", " ".join(raw.split())).strip())
        if not line or TRAILING_NOTICE.search(line):
            continue
        short = len(line) < 220
        if short and JUNK_LINE.search(line):
            continue
        if short and extra_junk is not None and extra_junk.search(line):
            continue
        lines.append(line)
    # Buang duplikat baris berurutan (judul ulang, keterangan foto ganda).
    deduped = [line for i, line in enumerate(lines) if i == 0 or line != lines[i - 1]]
    return "\n".join(deduped).strip()


def detect_language(text: str, declared: str | None) -> str:
    words = re.findall(r"[a-z]+", text.lower()[:4000])
    if not words:
        return (declared or "unknown")[:2]
    ratio = sum(1 for w in words if w in ID_STOPWORDS) / len(words)
    if ratio >= 0.04:
        return "id"
    return (declared or "other")[:2] if declared and not declared.startswith("id") else "other"


def extract_article(html: str, url: str, min_chars: int = 400,
                    extra_junk: re.Pattern[str] | None = None,
                    category_hint: str | None = None) -> ExtractedArticle:
    soup = BeautifulSoup(html, "lxml")
    ld = _article_ld(_json_ld(soup))

    link = soup.find("link", rel="canonical")
    page_canonical = link.get("href") if link and link.get("href", "").startswith("http") else None

    title = (ld.get("headline") or _meta(soup, ("og:title", "twitter:title")) or
             (soup.title.get_text(strip=True) if soup.title else "")).strip()

    if ld.get("isAccessibleForFree") in (False, "False", "false"):
        raise Paywalled("isAccessibleForFree=false")

    raw_body = trafilatura.extract(
        html, url=url, include_comments=False, include_tables=False, include_images=False,
        # deduplicate=True memakai cache global lintas panggilan: paragraf yang mirip dengan
        # artikel sebelumnya ikut terbuang. Duplikat baris ditangani clean_content.
        favor_precision=True, deduplicate=False, output_format="txt",
    )
    content = clean_content(_drop_title_line(raw_body or "", title), extra_junk)
    lowered = content.lower()
    if len(content) < min_chars:
        if any(marker in lowered or marker in html.lower()[:200000] for marker in PAYWALL_MARKERS):
            raise Paywalled("isi terpotong oleh paywall")
        raise NoContent(f"isi terlalu pendek ({len(content)} karakter)")

    published = None
    for candidate in (ld.get("datePublished"), _meta(soup, DATE_META_NAMES)):
        published = parse_datetime(candidate)
        if published:
            break
    if published is None:
        time_tag = soup.find("time", attrs={"datetime": True})
        published = parse_datetime(time_tag["datetime"]) if time_tag else None
    if published is None:
        meta = trafilatura.extract_metadata(html, default_url=url)
        if meta is not None and meta.date:
            published = parse_datetime(meta.date)

    author = _ld_author(ld.get("author")) or _meta(soup, AUTHOR_META_NAMES)
    if author and author.startswith("http"):
        author = None

    section = ld.get("articleSection")
    if isinstance(section, list):
        section = section[0] if section else None
    category = section or _meta(soup, ("article:section",)) or category_hint

    html_tag = soup.find("html")
    declared = (html_tag.get("lang") if html_tag else None) or _meta(soup, ("content-language", "language"))

    return ExtractedArticle(
        url=url,
        canonical_url=canonical_url(_same_site(page_canonical, url) or url),
        title=" ".join(title.split()),
        content=content,
        author=author,
        published_at=published,
        category=category,
        language=detect_language(content, (declared or "").lower() or None),
    )


def _drop_title_line(body: str, title: str) -> str:
    """Beberapa portal mengulang judul sebagai baris pertama isi."""
    lines = body.split("\n", 1)
    if title and lines and " ".join(lines[0].split()).lower() == " ".join(title.split()).lower():
        return lines[1] if len(lines) > 1 else ""
    return body


def _same_site(candidate: str | None, url: str) -> str | None:
    """Pakai rel=canonical hanya jika masih di situs yang sama.

    Artikel sindikasi sering menunjuk kanonis ke penerbit asal. Kalau dipakai, varian dari
    portal ini akan terbuang sebagai URL ganda, padahal setiap sumber perlu disimpan dan
    ditandai sebagai sindikasi.
    """
    from urllib.parse import urlsplit

    from app.dataset.services.http import site_key

    if not candidate:
        return None
    a, b = urlsplit(candidate).hostname or "", urlsplit(url).hostname or ""
    return candidate if a and site_key(a) == site_key(b) else None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
