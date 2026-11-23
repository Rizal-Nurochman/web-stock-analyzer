"""Parser RSS 2.0 dan Atom berbasis defusedxml (aman dari entity expansion)."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from defusedxml import ElementTree

from app.config import WIB

ATOM = "{http://www.w3.org/2005/Atom}"
CONTENT = "{http://purl.org/rss/1.0/modules/content/}"
SNIPPET_LIMIT = 500
_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


class FeedParseError(Exception):
    pass


@dataclass(frozen=True)
class ParsedItem:
    title: str
    link: str
    published_at: datetime | None
    snippet: str | None


def _clean(text: str | None) -> str:
    if not text:
        return ""
    without_tags = _TAG.sub(" ", html.unescape(text))
    return _SPACE.sub(" ", html.unescape(without_tags)).strip()


def parse_datetime(raw: str | None) -> datetime | None:
    """Kembalikan waktu UTC. Waktu tanpa zona dianggap WIB (sumber Indonesia)."""
    if not raw:
        return None
    value = raw.strip()
    parsed: datetime | None = None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=WIB)
    return parsed.astimezone(timezone.utc)


def _text(element, path: str) -> str | None:
    found = element.find(path)
    return found.text if found is not None and found.text else None


def parse_feed(content: bytes | str) -> list[ParsedItem]:
    try:
        root = ElementTree.fromstring(content)
    except Exception as exc:  # ParseError, DefusedXmlException
        raise FeedParseError("Respons bukan RSS yang valid") from exc

    items: list[ParsedItem] = []
    if root.tag == f"{ATOM}feed":
        for entry in root.findall(f"{ATOM}entry"):
            # Element tanpa anak bernilai False, jadi periksa None secara eksplisit.
            link_el = entry.find(f"{ATOM}link[@rel='alternate']")
            if link_el is None:
                link_el = entry.find(f"{ATOM}link")
            link = (link_el.get("href") if link_el is not None else "") or ""
            title = _clean(_text(entry, f"{ATOM}title"))
            published = _text(entry, f"{ATOM}published") or _text(entry, f"{ATOM}updated")
            summary = _clean(_text(entry, f"{ATOM}summary") or _text(entry, f"{ATOM}content"))
            if title and link:
                items.append(
                    ParsedItem(title, link.strip(), parse_datetime(published), summary[:SNIPPET_LIMIT] or None)
                )
        return items

    channel = root.find("channel")
    if root.tag != "rss" or channel is None:
        raise FeedParseError(f"Elemen akar tidak dikenal: {root.tag}")

    for item in channel.findall("item"):
        title = _clean(_text(item, "title"))
        link = (_text(item, "link") or _text(item, "guid") or "").strip()
        description = _text(item, "description") or _text(item, f"{CONTENT}encoded")
        snippet = _clean(description)[:SNIPPET_LIMIT] or None
        published = parse_datetime(_text(item, "pubDate"))
        if title and link.startswith(("http://", "https://")):
            items.append(ParsedItem(title, link, published, snippet))
    return items
