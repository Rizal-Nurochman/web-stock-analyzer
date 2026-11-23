"""Daftar emiten MVP beserta alias yang diperiksa untuk pemetaan berita."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Issuer:
    code: str
    name: str
    short_name: str
    # Pola regex, dicocokkan peka huruf besar-kecil dengan batas kata.
    aliases: tuple[str, ...]


# Catatan alias:
# - "Mandiri" saja tidak dipakai karena juga berarti "independen" dalam bahasa Indonesia.
# - Akhiran "Syariah" dikecualikan: BRI Syariah, BNI Syariah, dan Mandiri Syariah kini BSI,
#   sedangkan BCA Syariah tidak tercatat sebagai BBCA.
ISSUERS: dict[str, Issuer] = {
    "BBCA": Issuer(
        "BBCA",
        "PT Bank Central Asia Tbk",
        "BCA",
        (r"BBCA", r"Bank Central Asia", r"BCA(?!\s+Syariah)"),
    ),
    "BBRI": Issuer(
        "BBRI",
        "PT Bank Rakyat Indonesia (Persero) Tbk",
        "BRI",
        (r"BBRI", r"Bank Rakyat Indonesia", r"BRI(?!\s+Syariah)"),
    ),
    "BMRI": Issuer(
        "BMRI",
        "PT Bank Mandiri (Persero) Tbk",
        "Bank Mandiri",
        (r"BMRI", r"Bank Mandiri(?!\s+Syariah)"),
    ),
    "BBNI": Issuer(
        "BBNI",
        "PT Bank Negara Indonesia (Persero) Tbk",
        "BNI",
        (r"BBNI", r"Bank Negara Indonesia", r"BNI(?!\s+Syariah)"),
    ),
}

TICKER_CODES: tuple[str, ...] = tuple(ISSUERS)


def normalize_ticker(raw: str) -> str:
    """Terima 'bbca', 'BBCA.JK', atau 'IDX:BBCA' dan kembalikan 'BBCA'."""
    code = raw.strip().upper()
    if ":" in code:
        code = code.split(":", 1)[1]
    if code.endswith(".JK"):
        code = code[:-3]
    return code
