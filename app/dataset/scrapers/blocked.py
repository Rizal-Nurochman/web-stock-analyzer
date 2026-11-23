"""Portal yang menolak akses otomatis saat diperiksa (23 Nov 2026).

Program tidak mencoba melewati tantangan bot, mengganti User-Agent menjadi peramban, atau
memakai browser automation untuk menembus proteksi. Perintah check-sources tetap memeriksa
ulang aksesnya setiap dijalankan.
"""

from app.dataset.scrapers.base import UnavailablePortal


class Bisnis(UnavailablePortal):
    key = "bisnis"
    name = "Bisnis.com"
    homepage = "https://www.bisnis.com/"
    blocked_reason = ("Halaman dilindungi tantangan bot Cloudflare (HTTP 403). robots.txt juga "
                      "melarang /rss/ dan /feed/.")


class TempoBisnis(UnavailablePortal):
    key = "tempo_bisnis"
    name = "Tempo Bisnis"
    homepage = "https://bisnis.tempo.co/"
    blocked_reason = "Halaman utama, sitemap, dan RSS menolak akses otomatis (HTTP 403)."


class MediaIndonesia(UnavailablePortal):
    key = "mediaindonesia"
    name = "Media Indonesia"
    homepage = "https://mediaindonesia.com/"
    blocked_reason = "Halaman dilindungi tantangan bot Cloudflare (HTTP 403)."
