"""Statistik dan grafik analisis teknikal untuk laporan.

Memakai fungsi aplikasi (app.market.service.market_history) sehingga Bollinger Bands
identik dengan dashboard: Close, SMA 20 sesi harian, +/-2 standar deviasi sampel.

    python scripts/laporan/analisis_teknikal.py [path/ke/prices.db]

Keluaran: assets/laporan/teknikal_stats.json dan beberapa PNG di assets/laporan/.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app import db  # noqa: E402
from app.market.models import Price  # noqa: E402
from app.market.service import market_history  # noqa: E402

TICKERS = ("BBCA", "BBRI", "BMRI", "BBNI")
START = date(2023, 1, 1)
END = date(2026, 11, 23)
OUT = ROOT / "assets" / "laporan"
SPIKE_RATIO = 2.0  # volume > 2x rata-rata 20 sesi sebelumnya


def spearman(x: list[float], y: list[float]) -> float:
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = ranks(x), ranks(y)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else float("nan")


def analyse(session, ticker: str) -> dict:
    full = market_history(session, ticker)
    all_rows = session.query(Price).filter(Price.ticker == ticker).count()
    candles = [c for c in full if START <= c.session_date <= END]
    idx0 = full.index(candles[0])

    # Kualitas data pada seluruh histori tersimpan.
    dup = len(full) - len({c.session_date for c in full})
    bad_ohlc = sum(1 for c in full if not (c.low <= min(c.open, c.close) and max(c.open, c.close) <= c.high))
    zero_vol = sum(1 for c in full if c.volume == 0)

    closes = [c.close for c in candles]
    rets = [(full[idx0 + i].close / full[idx0 + i - 1].close - 1) for i in range(len(candles))]

    first, last = candles[0], candles[-1]
    hi = max(candles, key=lambda c: c.high)
    lo = min(candles, key=lambda c: c.low)

    # Per tahun: close akhir tahun, return, volatilitas tahunan, rata-rata volume.
    by_year = defaultdict(list)
    for c, r in zip(candles, rets):
        by_year[c.session_date.year].append((c, r))
    years = {}
    prev_close = full[idx0 - 1].close
    for year in sorted(by_year):
        rows = by_year[year]
        end_close = rows[-1][0].close
        years[year] = {
            "sesi": len(rows),
            "close_awal_tahun": rows[0][0].open,
            "close_akhir": end_close,
            "return_pct": round((end_close / prev_close - 1) * 100, 2),
            "volatilitas_tahunan_pct": round(statistics.stdev([r for _, r in rows]) * math.sqrt(252) * 100, 2),
            "rata2_volume_juta": round(statistics.fmean([c.volume for c, _ in rows]) / 1e6, 1),
            "naik": sum(1 for c, _ in rows if c.close > c.open),
            "turun": sum(1 for c, _ in rows if c.close < c.open),
        }
        prev_close = end_close

    # Bollinger: bandwidth, posisi harga, sentuhan band.
    bw = [((c.band.upper - c.band.lower) / c.band.middle, c) for c in candles if c.band]
    above = [c for c in candles if c.band and c.close > c.band.upper]
    below = [c for c in candles if c.band and c.close < c.band.lower]
    bw_sorted = sorted(bw, key=lambda t: t[0])

    def forward(cases, days):
        out = []
        for c in cases:
            i = full.index(c)
            if i + days < len(full):
                out.append(full[i + days].close / c.close - 1)
        return out

    fwd = {}
    for name, cases in (("close_di_bawah_lower", below), ("close_di_atas_upper", above)):
        for days in (5, 10):
            values = forward(cases, days)
            fwd[f"{name}_{days}h"] = {
                "kasus": len(values),
                "persen_naik": round(100 * sum(1 for v in values if v > 0) / len(values), 1) if values else None,
                "median_return_pct": round(statistics.median(values) * 100, 2) if values else None,
            }

    # Volume: lonjakan relatif terhadap rata-rata 20 sesi sebelumnya.
    spikes, ratio_abs = [], []
    for i, c in enumerate(candles):
        j = idx0 + i
        window = [x.volume for x in full[j - 20 : j]]
        if len(window) < 20 or not statistics.fmean(window):
            continue
        ratio = c.volume / statistics.fmean(window)
        ratio_abs.append((ratio, abs(rets[i]), (c.band.upper - c.band.lower) / c.band.middle if c.band else None))
        if ratio >= SPIKE_RATIO:
            spikes.append((c, ratio, rets[i]))
    top_vol = sorted(candles, key=lambda c: c.volume, reverse=True)[:5]

    rho_vol_absret = spearman([a for a, _, _ in ratio_abs], [b for _, b, _ in ratio_abs])
    pairs_bw = [(a, w) for a, _, w in ratio_abs if w is not None]
    rho_vol_bw = spearman([a for a, _ in pairs_bw], [w for _, w in pairs_bw])

    return {
        "ticker": ticker,
        "histori_tersimpan": {"baris": all_rows, "awal": str(full[0].session_date), "akhir": str(full[-1].session_date)},
        "kualitas": {"tanggal_duplikat": dup, "ohlc_tidak_konsisten": bad_ohlc, "volume_nol": zero_vol},
        "periode": {"awal": str(first.session_date), "akhir": str(last.session_date), "sesi": len(candles)},
        "harga": {
            "open_awal": first.open, "close_akhir": last.close,
            "perubahan_pct": round((last.close / full[idx0 - 1].close - 1) * 100, 2),
            "tertinggi": hi.high, "tgl_tertinggi": str(hi.session_date),
            "terendah": lo.low, "tgl_terendah": str(lo.session_date),
            "drawdown_dari_puncak_pct": round((last.close / hi.high - 1) * 100, 2),
            "return_harian_terbesar_pct": round(max(rets) * 100, 2),
            "tgl_return_terbesar": str(candles[rets.index(max(rets))].session_date),
            "return_harian_terkecil_pct": round(min(rets) * 100, 2),
            "tgl_return_terkecil": str(candles[rets.index(min(rets))].session_date),
            "hari_return_lebih_10pct": sum(1 for r in rets if abs(r) >= 0.10),
        },
        "tahunan": years,
        "bollinger": {
            "bandwidth_rata2_pct": round(statistics.fmean([w for w, _ in bw]) * 100, 2),
            "bandwidth_median_pct": round(statistics.median([w for w, _ in bw]) * 100, 2),
            "bandwidth_maks_pct": round(bw_sorted[-1][0] * 100, 2), "tgl_bandwidth_maks": str(bw_sorted[-1][1].session_date),
            "bandwidth_min_pct": round(bw_sorted[0][0] * 100, 2), "tgl_bandwidth_min": str(bw_sorted[0][1].session_date),
            "close_di_atas_upper": len(above), "close_di_bawah_lower": len(below),
            "persen_di_atas_upper": round(100 * len(above) / len(candles), 1),
            "persen_di_bawah_lower": round(100 * len(below) / len(candles), 1),
            "close_akhir_vs_band": {
                "upper": round(last.band.upper, 1), "middle": round(last.band.middle, 1),
                "lower": round(last.band.lower, 1), "close": last.close,
                "percent_b": round((last.close - last.band.lower) / (last.band.upper - last.band.lower), 3),
            },
            "return_setelah_sentuhan": fwd,
        },
        "volume": {
            "rata2_juta": round(statistics.fmean([c.volume for c in candles]) / 1e6, 1),
            "median_juta": round(statistics.median([c.volume for c in candles]) / 1e6, 1),
            "lonjakan_2x": len(spikes),
            "lonjakan_hari_turun": sum(1 for _, _, r in spikes if r < 0),
            "lonjakan_hari_naik": sum(1 for _, _, r in spikes if r > 0),
            "top5": [{"tanggal": str(c.session_date), "volume_juta": round(c.volume / 1e6, 1),
                      "return_pct": round(rets[candles.index(c)] * 100, 2)} for c in top_vol],
            "spearman_rasio_volume_vs_abs_return": round(rho_vol_absret, 3),
            "spearman_rasio_volume_vs_bandwidth": round(rho_vol_bw, 3),
            "n_observasi": len(ratio_abs),
        },
        "_series": {
            "dates": [str(c.session_date) for c in candles],
            "close": closes,
            "bandwidth": [((c.band.upper - c.band.lower) / c.band.middle) if c.band else None for c in candles],
            "ratio_abs": ratio_abs,
        },
    }


def figures(results: dict) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from datetime import datetime

    ink, ink2, grid, series = "#0b0b0b", "#52514e", "#e6e4de", "#2a78d6"
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": ink2,
                         "axes.labelcolor": ink2, "xtick.color": ink2, "ytick.color": ink2})

    # Gambar: lebar Bollinger Bands per emiten (small multiples, satu hue, skala sama).
    fig, axes = plt.subplots(4, 1, figsize=(9, 8.2), sharex=True, sharey=True)
    for ax, t in zip(axes, TICKERS):
        s = results[t]["_series"]
        xs = [datetime.fromisoformat(d) for d, w in zip(s["dates"], s["bandwidth"]) if w is not None]
        ys = [w * 100 for w in s["bandwidth"] if w is not None]
        ax.plot(xs, ys, color=series, linewidth=1.4)
        ax.set_title(t, loc="left", fontsize=10, color=ink, fontweight="bold")
        ax.grid(axis="y", color=grid, linewidth=0.8)
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_ylabel("Lebar band (%)")
    axes[-1].xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 7)))
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    fig.suptitle("Lebar Bollinger Bands (Upper - Lower) / Middle, sesi harian 2023-2026", x=0.01, ha="left",
                 fontsize=11, color=ink)
    fig.tight_layout()
    fig.savefig(OUT / "teknikal_bandwidth.png", dpi=160)
    plt.close(fig)

    # Gambar: rasio volume vs |return| (small multiples, sumbu x log).
    fig, axes = plt.subplots(2, 2, figsize=(9, 6.4), sharex=True, sharey=True)
    for ax, t in zip(axes.flat, TICKERS):
        pts = results[t]["_series"]["ratio_abs"]
        ax.scatter([p[0] for p in pts], [p[1] * 100 for p in pts], s=10, color=series, alpha=0.45,
                   edgecolors="none")
        ax.set_xscale("log")
        ax.axvline(SPIKE_RATIO, color=ink2, linewidth=0.8, linestyle="--")
        rho = results[t]["volume"]["spearman_rasio_volume_vs_abs_return"]
        ax.set_title(f"{t}  (Spearman ρ = {rho:.2f})", loc="left", fontsize=10, color=ink)
        ax.grid(color=grid, linewidth=0.8)
        ax.spines[["top", "right"]].set_visible(False)
    for ax in axes[1]:
        ax.set_xlabel("Volume / rata-rata 20 sesi sebelumnya (skala log)")
    for ax in axes[:, 0]:
        ax.set_ylabel("|Return harian| (%)")
    fig.suptitle("Rasio volume terhadap besar perubahan harga harian, 2023-2026 (garis putus = 2x)",
                 x=0.01, ha="left", fontsize=11, color=ink)
    fig.tight_layout()
    fig.savefig(OUT / "teknikal_volume_vs_return.png", dpi=160)
    plt.close(fig)


def main() -> None:
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "report_prices.db"
    db.configure(f"sqlite:///{db_path}")
    OUT.mkdir(parents=True, exist_ok=True)
    with db.get_session_factory()() as session:
        results = {t: analyse(session, t) for t in TICKERS}
    figures(results)
    clean = {t: {k: v for k, v in r.items() if not k.startswith("_")} for t, r in results.items()}
    (OUT / "teknikal_stats.json").write_text(json.dumps(clean, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(clean, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
