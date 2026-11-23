"""URL kanonis untuk menyatukan artikel yang sama lintas kanal."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PREFIXES = ("utm_", "fbclid", "gclid")
TRACKING_KEYS = {"ref", "source", "src", "rss", "tag_from", "_ga", "single"}

_ANTARA_ID = re.compile(r"^/berita/(\d+)")
_DETIK_ID = re.compile(r"/d-(\d+)")


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    for prefix in ("www.", "m.", "amp."):
        if host.startswith(prefix):
            host = host[len(prefix) :]

    path = parts.path or "/"
    if path.endswith("/amp"):
        path = path[: -len("/amp")]
    path = path.rstrip("/") or "/"

    # ANTARA Finansial dan ANTARA Bursa memuat artikel yang sama dengan slug yang bisa berbeda.
    if host == "antaranews.com":
        match = _ANTARA_ID.match(path)
        if match:
            return f"https://antaranews.com/berita/{match.group(1)}"

    if host.endswith("detik.com"):
        match = _DETIK_ID.search(path)
        if match:
            return f"https://{host}/d-{match.group(1)}"

    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=False)
        if not key.lower().startswith(TRACKING_PREFIXES) and key.lower() not in TRACKING_KEYS
    ]
    query.sort()
    return urlunsplit(("https", host, path, urlencode(query), ""))
