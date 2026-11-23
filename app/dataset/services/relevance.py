"""Penentuan relevansi artikel terhadap BBRI, BMRI, BBCA, dan BBNI.

Aturan per emiten:
1. Frasa yang merujuk entitas lain (BRI Syariah, BRI Liga 1, Desa Mandiri, ...) dihapus dulu.
2. Sebutan kuat (ticker, nama resmi, "Bank BRI") selalu dihitung.
3. Sebutan lemah (BRI, BNI, BCA, Mandiri) hanya dihitung bila kalimatnya memuat konteks
   perbankan atau pasar modal.
4. Emiten "relevant" bila menjadi objek pembahasan: disebut di judul, atau berulang
   (>= 3 kali), atau muncul di paragraf pembuka dan disebut lagi; artikelnya juga harus
   memuat konteks bisnis/keuangan.
5. Selain itu, setiap sebutan yang sah menjadikan emiten "review": manusia yang memutuskan.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.dataset.config.keywords import BANKING_CONTEXT, MARKET_CONTEXT, STOCKS, StockTerms
from app.dataset.models.types import StockMatch

_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")


def _word_patterns(words: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile(r"\b(?:" + "|".join(re.escape(w) for w in words) + r")\b", re.IGNORECASE)


BANK_CTX = _word_patterns(BANKING_CONTEXT)
MARKET_CTX = _word_patterns(MARKET_CONTEXT)


@dataclass
class _Compiled:
    terms: StockTerms
    strong: list[re.Pattern[str]]
    weak: list[re.Pattern[str]]
    exclude: list[re.Pattern[str]]


_COMPILED = {
    code: _Compiled(
        terms,
        [re.compile(p) for p in terms.strong],
        [re.compile(p) for p in terms.weak],
        [re.compile(p) for p in terms.exclude],
    )
    for code, terms in STOCKS.items()
}

LEAD_CHARS = 600

# Konten layanan/konsumen: menyebut bank, tetapi bukan pembahasan emiten sebagai objek
# pasar (kurs harian per bank, cara setor tunai, syarat KUR, promo). Selalu ke review.
SERVICE_TITLE = re.compile(
    r"^(cara|syarat|tabel angsuran|simulasi|kode (bank|transfer)|jam operasional|"
    r"jadwal operasional|promo|kode promo|tips)\b|"
    r"\bkurs (dollar|dolar|rupiah|euro|yen|yuan|ringgit|riyal|usd)\b.*\b(di|bank) (bri|bni|bca|mandiri)\b|"
    r"\b(cara|syarat) (daftar|buka|setor|transfer|cek|bayar|ajukan|mengajukan|pinjam|membuat|aktivasi)|"
    # Artikel penjelas produk. "Penyaluran KUR BRI" (metrik kinerja) sengaja tidak tertangkap.
    r"^(apa itu|apa saja|ketahui|kenali|mengenal|begini cara|berikut cara|panduan)\b|"
    r"\b(info|syarat|tabel|simulasi|angsuran) kur\b|"
    r"\b(biaya admin|swift code|kode swift|limit transfer|limit tarik)\b|"
    # Daftar suku bunga harian per bank. "BRI naikkan bunga deposito" (kebijakan) tetap lolos.
    r"^(daftar|cek|simak|update|ini)\b.*\bbunga (deposito|tabungan|kpr)\b",
    re.IGNORECASE,
)
MIN_BUSINESS_TERMS = 2


def _mask(text: str, patterns: list[re.Pattern[str]]) -> str:
    for pattern in patterns:
        text = pattern.sub(lambda m: " " * len(m.group(0)), text)
    return text


def _has_context(sentence: str) -> bool:
    return bool(BANK_CTX.search(sentence) or MARKET_CTX.search(sentence))


def _count(text: str, stock: _Compiled) -> tuple[int, int, list[str], list[int], int]:
    """Kembalikan (sebutan kuat, sebutan lemah berkonteks, istilah, posisi, lemah tanpa konteks)."""
    masked = _mask(text, stock.exclude)
    strong_spans: list[tuple[int, int]] = []
    terms: list[str] = []
    positions: list[int] = []
    for pattern in stock.strong:
        for m in pattern.finditer(masked):
            strong_spans.append(m.span())
            terms.append(m.group(0))
            positions.append(m.start())
    weak = 0
    bare = 0
    offset = 0
    for sentence in _SENTENCE.split(masked):
        start = masked.find(sentence, offset)
        offset = start + len(sentence) if start >= 0 else offset
        for pattern in stock.weak:
            for m in pattern.finditer(sentence):
                absolute = start + m.start()
                # Bagian dari sebutan kuat ("Bank BRI") tidak dihitung dua kali.
                if any(a <= absolute < b for a, b in strong_spans):
                    continue
                if _has_context(sentence):
                    weak += 1
                    terms.append(m.group(0))
                    positions.append(absolute)
                else:
                    bare += 1
    return len(strong_spans), weak, terms, positions, bare


def business_terms(text: str) -> set[str]:
    found = {m.group(0).lower() for m in MARKET_CTX.finditer(text)}
    found |= {m.group(0).lower() for m in BANK_CTX.finditer(text)
              if m.group(0).lower() not in {"bank", "transaksi"}}
    return found


def classify(title: str, content: str) -> list[StockMatch]:
    """Kembalikan emiten yang disebut secara sah, masing-masing relevant atau review."""
    body = content or ""
    service_content = bool(SERVICE_TITLE.search(title.strip()))
    business = business_terms(title + "\n" + body)
    has_business = len(business) >= MIN_BUSINESS_TERMS
    results: list[StockMatch] = []

    for code, stock in _COMPILED.items():
        t_strong, t_weak, t_terms, _, t_bare = _count(title, stock)
        # Judul sering huruf kapital semua kata; sebutan lemah di judul butuh konteks di judul
        # itu sendiri atau sebutan kuat di isi.
        b_strong, b_weak, b_terms, b_pos, b_bare = _count(body, stock)
        in_title = t_strong > 0 or (t_weak > 0 and (b_strong > 0 or b_weak > 0))
        mentions = b_strong + b_weak + (1 if in_title else 0)
        if mentions == 0:
            # Alias pendek berulang tanpa konteks (mis. berita CSR "BRI gelar lomba lari"):
            # mungkin bank ini, mungkin bukan. Serahkan ke manusia, jangan dibuang diam-diam.
            if t_bare + b_bare >= 2:
                results.append(StockMatch(
                    code=code, name=stock.terms.name, relevance="review", score=0.5,
                    mention_count=b_bare, in_title=t_bare > 0,
                    matched_terms=[stock.terms.weak[0].replace(r"\b", "")],
                    reasons=[f"alias pendek {t_bare + b_bare} kali tanpa konteks perbankan/pasar"]))
            continue

        in_lead = any(p < LEAD_CHARS for p in b_pos)
        strong_total = t_strong + b_strong
        reasons: list[str] = []
        if in_title:
            reasons.append("disebut di judul")
        if b_strong + b_weak >= 3:
            reasons.append(f"disebut {b_strong + b_weak} kali di isi")
        if in_lead:
            reasons.append("disebut di paragraf pembuka")

        central = in_title or (b_strong + b_weak) >= 3 or (in_lead and (b_strong + b_weak) >= 2)
        identified = strong_total > 0 or (b_weak + t_weak) >= 2
        if not has_business:
            reasons.append("tanpa konteks bisnis/keuangan")
        if not identified:
            reasons.append("hanya alias pendek")
        if not central:
            reasons.append("sebutan sambil lalu")

        if service_content:
            reasons.append("konten layanan/konsumen, bukan pembahasan emiten")
        relevance = "relevant" if (central and identified and has_business and not service_content) else "review"
        score = 3.0 * strong_total + 1.0 * (b_weak + t_weak) + (3.0 if in_title else 0) + (1.0 if in_lead else 0)
        results.append(
            StockMatch(
                code=code,
                name=stock.terms.name,
                relevance=relevance,
                score=round(score, 2),
                mention_count=b_strong + b_weak,
                in_title=in_title,
                matched_terms=sorted(set(t_terms + b_terms)),
                reasons=reasons,
            )
        )
    return results


def article_status(matches: list[StockMatch]) -> str | None:
    if not matches:
        return None
    return "relevant" if any(m.relevance == "relevant" for m in matches) else "review"


def target_sentences(code: str, title: str, content: str, limit: int = 8) -> list[str]:
    """Judul dan kalimat isi yang benar-benar menyebut emiten ini (dasar sentimen per target)."""
    stock = _COMPILED[code]
    picked: list[str] = []
    for sentence in [title, *_SENTENCE.split(content or "")]:
        text = " ".join(sentence.split())
        if not text:
            continue
        masked = _mask(text, stock.exclude)
        strong = any(p.search(masked) for p in stock.strong)
        weak = any(p.search(masked) for p in stock.weak) and _has_context(text)
        if strong or weak:
            picked.append(text)
            if len(picked) >= limit:
                break
    return picked
