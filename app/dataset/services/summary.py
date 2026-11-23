"""Ringkasan hasil pengumpulan: tabel konsol dan laporan HTML dengan grafik SVG sederhana."""

from __future__ import annotations

import html
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import func, select

from app.dataset.config.keywords import STOCKS
from app.dataset.database.session import Database
from app.dataset.models.schema import Article, ArticleStock, SeenUrl, SourceStatus

FAILED_STATUSES = ("no_content", "paywalled", "failed", "blocked")


@dataclass
class Summary:
    total_relevant: int = 0
    total_review: int = 0
    per_source: dict[str, int] = field(default_factory=dict)
    per_stock: dict[str, int] = field(default_factory=dict)
    multi_stock: int = 0
    duplicates: int = 0
    failed_extraction: dict[str, int] = field(default_factory=dict)
    per_month: dict[str, int] = field(default_factory=dict)
    per_month_stock: dict[str, dict[str, int]] = field(default_factory=dict)
    sources: list[tuple[str, str, str, str]] = field(default_factory=list)
    labelled_pairs: int = 0


def build_summary(db: Database) -> Summary:
    out = Summary()
    with db.read() as s:
        out.total_relevant = s.scalar(select(func.count()).select_from(Article)
                                      .where(Article.relevance_status == "relevant")) or 0
        out.total_review = s.scalar(select(func.count()).select_from(Article)
                                    .where(Article.relevance_status == "review")) or 0
        out.per_source = dict(s.execute(
            select(Article.source, func.count()).where(Article.relevance_status == "relevant")
            .group_by(Article.source).order_by(func.count().desc())).all())
        rows = s.execute(
            select(ArticleStock.article_id, ArticleStock.stock_code, Article.published_at)
            .join(Article, Article.article_id == ArticleStock.article_id)
            .where(Article.relevance_status == "relevant", ArticleStock.relevance == "relevant",
                   ArticleStock.review_status != "rejected")).all()
        per_article = Counter(r.article_id for r in rows)
        out.multi_stock = sum(1 for n in per_article.values() if n > 1)
        out.per_stock = {code: 0 for code in STOCKS}
        for r in rows:
            out.per_stock[r.stock_code] += 1
            month = (r.published_at or "tanpa tanggal")[:7]
            out.per_month_stock.setdefault(month, {c: 0 for c in STOCKS})[r.stock_code] += 1
        months = Counter((p or "tanpa tanggal")[:7] for p in s.scalars(
            select(Article.published_at).where(Article.relevance_status == "relevant")))
        out.per_month = dict(sorted(months.items()))
        out.duplicates = s.scalar(select(func.count()).select_from(Article)
                                  .where(Article.is_duplicate.is_(True))) or 0
        out.failed_extraction = dict(s.execute(
            select(SeenUrl.status, func.count()).where(SeenUrl.status.in_(FAILED_STATUSES))
            .group_by(SeenUrl.status)).all())
        out.sources = [(r.source, r.name, r.status, r.note or "") for r in s.scalars(select(SourceStatus))]
        out.labelled_pairs = s.scalar(select(func.count()).select_from(ArticleStock)
                                      .where(ArticleStock.manual_sentiment.is_not(None))) or 0
    return out


def format_console(summary: Summary) -> str:
    lines = [
        "RINGKASAN DATASET",
        f"  Artikel relevan (dataset utama) : {summary.total_relevant}",
        f"  Artikel perlu review            : {summary.total_review}",
        f"  Artikel membahas >1 emiten      : {summary.multi_stock}",
        f"  Artikel duplikat/sindikasi      : {summary.duplicates}",
        f"  Gagal diekstrak                 : {sum(summary.failed_extraction.values())} "
        + str(summary.failed_extraction or ""),
        f"  Pasangan berlabel manual        : {summary.labelled_pairs}",
        "",
        "Per emiten:",
        *[f"  {code}: {n}" for code, n in summary.per_stock.items()],
        "",
        "Per portal:",
        *[f"  {name}: {n}" for name, n in summary.per_source.items()],
        "",
        "Per bulan:",
        *[f"  {month}: {n}" for month, n in summary.per_month.items()],
    ]
    return "\n".join(lines)


def _bar_svg(data: dict[str, int], width: int = 560) -> str:
    if not data:
        return "<p class='empty'>Belum ada data.</p>"
    top = max(data.values()) or 1
    row = 28
    parts = [f'<svg viewBox="0 0 {width} {row * len(data) + 8}" role="img" aria-label="Jumlah berita per emiten">']
    for i, (label, value) in enumerate(data.items()):
        y = i * row + 4
        w = (width - 170) * value / top
        parts.append(f'<text x="0" y="{y + 17}" class="lbl">{html.escape(label)}</text>'
                     f'<rect x="70" y="{y + 4}" width="{w:.1f}" height="18" rx="3" class="bar"/>'
                     f'<text x="{76 + w:.1f}" y="{y + 17}" class="val">{value}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _line_svg(series: dict[str, dict[str, int]], width: int = 760, height: int = 260) -> str:
    months = [m for m in sorted(series) if m != "tanpa tanggal"]
    if len(months) < 2:
        return "<p class='empty'>Butuh minimal dua bulan data untuk grafik tren.</p>"
    codes = list(STOCKS)
    top = max(max(series[m].values()) for m in months) or 1
    left, bottom, right, topm = 40, 30, 10, 10
    plot_w, plot_h = width - left - right, height - bottom - topm
    step = plot_w / (len(months) - 1)
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Jumlah berita per bulan per emiten">',
             f'<line x1="{left}" y1="{topm + plot_h}" x2="{width - right}" y2="{topm + plot_h}" class="axis"/>',
             f'<text x="{left - 6}" y="{topm + 4}" class="tick" text-anchor="end">{top}</text>',
             f'<text x="{left - 6}" y="{topm + plot_h}" class="tick" text-anchor="end">0</text>']
    for i, m in enumerate(months):
        if i % max(1, len(months) // 8) == 0 or i == len(months) - 1:
            parts.append(f'<text x="{left + i * step:.1f}" y="{height - 8}" class="tick" text-anchor="middle">{m}</text>')
    for idx, code in enumerate(codes):
        pts = " ".join(f"{left + i * step:.1f},{topm + plot_h - plot_h * series[m][code] / top:.1f}"
                       for i, m in enumerate(months))
        parts.append(f'<polyline points="{pts}" class="s{idx}"/>')
    parts.append("</svg>")
    legend = "".join(f'<span><i class="k{i}"></i>{c}</span>' for i, c in enumerate(codes))
    return "".join(parts) + f'<div class="legend">{legend}</div>'


def write_html(summary: Summary, path: Path) -> Path:
    source_rows = "".join(
        f"<tr><td>{html.escape(name)}</td><td>{html.escape(status)}</td>"
        f"<td>{summary.per_source.get(name, 0)}</td><td>{html.escape(note)}</td></tr>"
        for _, name, status, note in summary.sources)
    month_rows = "".join(f"<tr><td>{m}</td><td>{n}</td></tr>" for m, n in summary.per_month.items())
    doc = f"""<!doctype html><html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ringkasan Dataset Berita Perbankan</title>
<style>
body{{font-family:system-ui,sans-serif;margin:0;padding:24px 16px;color:#1d1d24;background:#fafafa;line-height:1.5}}
main{{max-width:900px;margin:0 auto}} h1{{font-size:24px}} h2{{font-size:17px;margin-top:32px}}
.kpi{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:8px}}
.kpi div{{background:#fff;border:1px solid #e2e2e8;border-radius:8px;padding:10px 12px}}
.kpi b{{display:block;font-size:22px}} table{{border-collapse:collapse;width:100%;background:#fff;font-size:13px}}
td,th{{border:1px solid #e2e2e8;padding:6px 8px;text-align:left;vertical-align:top}}
svg{{width:100%;height:auto;background:#fff;border:1px solid #e2e2e8;border-radius:8px}}
.lbl,.val,.tick{{font-size:12px;fill:#444}} .bar{{fill:#3b5bdb}} .axis{{stroke:#999}}
polyline{{fill:none;stroke-width:2}} .s0{{stroke:#1c7ed6}}.s1{{stroke:#e8590c}}.s2{{stroke:#2b8a3e}}.s3{{stroke:#ae3ec9}}
.legend{{display:flex;gap:16px;font-size:13px;margin-top:6px}} .legend i{{display:inline-block;width:12px;height:3px;margin-right:6px;vertical-align:middle}}
.k0{{background:#1c7ed6}}.k1{{background:#e8590c}}.k2{{background:#2b8a3e}}.k3{{background:#ae3ec9}} .empty{{color:#666}}
</style></head><body><main>
<h1>Ringkasan Dataset Berita Perbankan</h1>
<div class="kpi">
<div>Artikel relevan<b>{summary.total_relevant}</b></div>
<div>Perlu review<b>{summary.total_review}</b></div>
<div>Membahas &gt;1 emiten<b>{summary.multi_stock}</b></div>
<div>Duplikat/sindikasi<b>{summary.duplicates}</b></div>
<div>Gagal diekstrak<b>{sum(summary.failed_extraction.values())}</b></div>
</div>
<h2>Jumlah berita per emiten</h2>{_bar_svg(summary.per_stock)}
<h2>Perkembangan per bulan</h2>{_line_svg(summary.per_month_stock)}
<h2>Per portal</h2><table><tr><th>Portal</th><th>Status akses</th><th>Artikel relevan</th><th>Catatan</th></tr>{source_rows}</table>
<h2>Distribusi bulan</h2><table><tr><th>Bulan</th><th>Artikel</th></tr>{month_rows}</table>
</main></body></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc, encoding="utf-8")
    return path
