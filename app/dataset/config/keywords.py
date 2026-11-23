"""Kamus emiten, konteks perbankan, dan konteks pasar modal untuk filter relevansi.

Pola dicocokkan peka huruf besar-kecil kecuali disebut lain. Alias pendek (BRI, BNI, BCA,
Mandiri) diperlakukan sebagai sebutan lemah: baru dihitung jika kalimatnya memuat
konteks perbankan atau pasar modal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class StockTerms:
    code: str
    name: str
    strong: tuple[str, ...]
    weak: tuple[str, ...]
    # Frasa yang dihapus sebelum menghitung sebutan, karena merujuk entitas lain.
    exclude: tuple[str, ...]


STOCKS: dict[str, StockTerms] = {
    "BBRI": StockTerms(
        code="BBRI",
        name="PT Bank Rakyat Indonesia (Persero) Tbk",
        strong=(
            r"\bBBRI\b",
            r"\bBank Rakyat Indonesia\b",
            r"\bBank BRI\b",
            r"\bBRI \(Persero\)",
            r"\bBRI Tbk\b",
            r"\bPT\.? BRI\b",
        ),
        weak=(r"\bBRI\b",),
        exclude=(
            r"\bBRI Syariah\b",           # kini BSI (BRIS), emiten berbeda
            r"\bBRI Liga 1\b",            # nama kompetisi sepak bola
            r"\bBRI Super League\b",
            r"\bBRI Liga\b",
        ),
    ),
    "BMRI": StockTerms(
        code="BMRI",
        name="PT Bank Mandiri (Persero) Tbk",
        strong=(
            r"\bBMRI\b",
            r"\bBank Mandiri\b",
            r"\bMandiri \(Persero\)",
            r"\bMandiri Tbk\b",
        ),
        # Huruf kapital wajib: "mandiri" kecil berarti independen.
        weak=(r"\bMandiri\b",),
        exclude=(
            r"\bBank Syariah Mandiri\b",
            r"\bMandiri Syariah\b",
            r"\bDesa Mandiri\b",
            r"\bMandiri Energi\b",
            r"\bKampung Mandiri\b",
            r"\bWirausaha Mandiri\b",
            r"\bKurikulum Merdeka Mandiri\b",
            r"\bJalur Mandiri\b",         # jalur masuk perguruan tinggi
            r"\bSeleksi Mandiri\b",
            r"\bTol Mandiri\b",
            r"\bMandiri Pangan\b",
        ),
    ),
    "BBCA": StockTerms(
        code="BBCA",
        name="PT Bank Central Asia Tbk",
        strong=(
            r"\bBBCA\b",
            r"\bBank Central Asia\b",
            r"\bBank BCA\b",
            r"\bBCA Tbk\b",
            r"\bPT\.? BCA\b",
        ),
        weak=(r"\bBCA\b",),
        exclude=(r"\bBCA Syariah\b",),    # anak usaha, tidak tercatat sebagai BBCA
    ),
    "BBNI": StockTerms(
        code="BBNI",
        name="PT Bank Negara Indonesia (Persero) Tbk",
        strong=(
            r"\bBBNI\b",
            r"\bBank Negara Indonesia\b",
            r"\bBank BNI\b",
            r"\bBNI \(Persero\)",
            r"\bBNI Tbk\b",
            r"\bPT\.? BNI\b",
        ),
        weak=(r"\bBNI\b",),
        exclude=(r"\bBNI Syariah\b",),    # kini BSI
    ),
}

# Konteks yang membuat alias pendek layak dihitung (dicocokkan tanpa peka huruf).
BANKING_CONTEXT = (
    "bank", "perbankan", "nasabah", "kredit", "tabungan", "rekening", "deposito",
    "atm", "kartu kredit", "kpr", "kur", "pembiayaan", "bumn", "himbara", "persero",
    "tbk", "ojk", "bank indonesia", "dirut", "direktur utama", "brimo", "livin",
    "mybca", "wondr", "qris", "transaksi", "dana pihak ketiga", "dpk",
)
MARKET_CONTEXT = (
    "saham", "emiten", "ihsg", "bursa", "bei", "investor", "dividen", "rups",
    "laba", "pendapatan", "kinerja", "aset", "npl", "obligasi", "buyback", "right issue",
    "rights issue", "akuisisi", "merger", "suku bunga", "bi rate", "bi-rate", "valuasi",
    "target harga", "rekomendasi", "net buy", "net sell", "beli bersih", "jual bersih",
    "asing", "kapitalisasi", "margin", "nim", "casa", "fee based", "laporan keuangan",
    "kuartal", "semester", "triwulan", "pertumbuhan", "prospek", "risiko", "rating",
    "price to book", "pbv", "harga saham", "market cap", "outlook",
)

# Prafilter judul/slug sebelum artikel diunduh: lebar, karena keputusan akhir ada di isi.
PREFILTER = re.compile(
    r"\b(bbri|bmri|bbca|bbni|bri|bni|bca|mandiri|bank rakyat|bank negara indonesia|"
    r"bank central asia|himbara|bank bumn|bank pelat merah|bank jumbo|bank besar|"
    r"big ?(4|four|banks?)|saham bank|saham perbankan|saham big)\b",
    re.IGNORECASE,
)


def compile_terms(patterns: tuple[str, ...]) -> list[re.Pattern[str]]:
    return [re.compile(p) for p in patterns]
