"""Hitung metrik fundamental dari data mentah Yahoo. Fungsi murni, tanpa I/O.

Konvensi:
- Laba = laba bersih yang dapat diatribusikan ke pemilik entitas induk
  (NetIncomeCommonStockholders), sama dengan dasar EPS.
- TTM = 4 kuartal terakhir menurut seri trailing Yahoo.
- Annualised = total kuartal tahun berjalan (YTD) x 4 / jumlah kuartal.
- Rasio harga memakai harga terkini quoteSummary, jadi ikut berubah tiap hari bursa.
- Rasio neraca memakai posisi kuartal terakhir (ROA/ROE: rata-rata awal dan akhir 4 kuartal
  bila posisi setahun sebelumnya tersedia).

Metrik yang tidak bisa dihitung dari data yang ada dikembalikan sebagai None, tidak ditebak.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

Series = dict[str, list[tuple[str, float]]]

# Metrik yang diminta tetapi tidak tersedia di Yahoo, atau tidak bermakna untuk bank.
UNAVAILABLE = [
    ("NPL gross, NPL coverage, CAR, CASA, cost of credit, NIM",
     "Rasio regulasi bank tidak dipublikasikan Yahoo. Sumbernya laporan publikasi bank (OJK)."),
    ("EV/EBITDA, ROCE, ROIC",
     "EBITDA dan modal yang diinvestasikan tidak bermakna untuk bank, dan Yahoo tidak menyediakannya."),
    ("Gross margin, current ratio, quick ratio, DSO, DIO, DPO",
     "Bank tidak punya harga pokok, persediaan, atau aset/liabilitas lancar."),
    ("Cum date dan pay date dividen",
     "Yahoo hanya memberi ex date. Cum date dan tanggal bayar ada di pengumuman KSEI/BEI."),
]


@dataclass(frozen=True)
class Point:
    when: str
    value: float


def _points(series: Series, name: str) -> list[Point]:
    return [Point(d, v) for d, v in series.get(name, [])]


def _latest(series: Series, name: str) -> Point | None:
    points = _points(series, name)
    return points[-1] if points else None


def _at(series: Series, name: str, when: str) -> float | None:
    for d, v in series.get(name, []):
        if d == when:
            return v
    return None


def _div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def _growth(now: float | None, before: float | None) -> float | None:
    """Persentase perubahan. Basis negatif atau nol tidak bermakna sebagai pertumbuhan."""
    if now is None or before is None or before <= 0:
        return None
    return (now / before - 1) * 100


def _positive_multiple(a: float | None, b: float | None) -> float | None:
    """Kelipatan valuasi hanya bermakna bila penyebutnya positif."""
    if b is None or b <= 0:
        return None
    return _div(a, b)


def _year_ago(when: str) -> str:
    d = date.fromisoformat(when)
    return d.replace(year=d.year - 1).isoformat()


def _quarter_label(when: str) -> str:
    d = date.fromisoformat(when)
    return f"Q{(d.month - 1) // 3 + 1} {d.year}"


def _epoch_date(value) -> str | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _ytd(series: Series, name: str, year: int, quarters: int) -> float | None:
    """Jumlah Q1..Qn tahun tertentu. None bila ada kuartal yang hilang."""
    months = ("03-31", "06-30", "09-30", "12-31")[:quarters]
    values = [_at(series, name, f"{year}-{m}") for m in months]
    if any(v is None for v in values):
        return None
    return sum(values)


def _ytd_quarters(series: Series, name: str, year: int) -> int:
    """Banyaknya kuartal berurutan sejak Q1 yang tersedia pada tahun tersebut."""
    n = 0
    for m in ("03-31", "06-30", "09-30", "12-31"):
        if _at(series, name, f"{year}-{m}") is None:
            break
        n += 1
    return n


def _average_balance(series: Series, name: str, latest: Point | None) -> tuple[float | None, str]:
    if latest is None:
        return None, ""
    before = _at(series, name, _year_ago(latest.when))
    if before is None:
        return latest.value, "posisi akhir"
    return (latest.value + before) / 2, "rata-rata awal dan akhir periode"


def item(key: str, label: str, value, unit: str, basis: str | None = None, hint: str | None = None) -> dict:
    return {"key": key, "label": label, "value": value, "unit": unit, "basis": basis, "hint": hint}


def _dividend_view(dividends: list[tuple[str, float]], detail: dict, stats: dict, calendar: dict, today: date) -> dict:
    """Dividen TTM dari riwayat ex date, ditambah dividen terjadwal yang sudah diumumkan."""
    past = [(d, a) for d, a in dividends if d <= today.isoformat()]
    year_ago = today.replace(year=today.year - 1).isoformat()
    if dividends:
        ttm = sum(a for d, a in past if d > year_ago)
    else:
        # Tanpa riwayat, pakai angka Yahoo hanya bila positif: nilai 0 di sana sering berarti data kosong.
        ttm = detail.get("trailingAnnualDividendRate") or None
    last = past[-1] if past else None

    upcoming = None
    ex_next = _epoch_date(detail.get("exDividendDate") or calendar.get("exDividendDate"))
    if ex_next and ex_next > today.isoformat():
        amount = stats.get("lastDividendValue") if _epoch_date(stats.get("lastDividendDate")) == ex_next else None
        upcoming = (ex_next, amount)
    return {"ttm": ttm, "last": last, "upcoming": upcoming,
            "history": [{"ex_date": d, "amount": a} for d, a in reversed(dividends)]}


def compute(series: Series, summary: dict, dividends: list[tuple[str, float]] | None = None,
            today: date | None = None) -> dict:
    price_mod = summary.get("price") or {}
    detail = summary.get("summaryDetail") or {}
    stats = summary.get("defaultKeyStatistics") or {}
    calendar = summary.get("calendarEvents") or {}

    q = lambda n: f"quarterly{n}"  # noqa: E731
    t = lambda n: f"trailing{n}"  # noqa: E731
    a = lambda n: f"annual{n}"  # noqa: E731

    price = price_mod.get("regularMarketPrice")
    latest_shares = _latest(series, q("OrdinarySharesNumber"))
    shares = stats.get("sharesOutstanding") or (latest_shares.value if latest_shares else None)
    float_shares = stats.get("floatShares")
    market_cap = price * shares if price is not None and shares else None

    rev_q = _latest(series, q("TotalRevenue"))
    ni_q = _latest(series, q("NetIncomeCommonStockholders"))
    quarter_end = max((p.when for p in (rev_q, ni_q) if p), default=None)

    def ttm(name: str) -> Point | None:
        point = _latest(series, t(name))
        # Titik trailing lama (Yahoo kadang menyisakan satu titik tahun lalu) bukan TTM terkini.
        if point and quarter_end and point.when < quarter_end:
            return None
        return point

    rev_ttm = ttm("TotalRevenue")
    ni_ttm = ttm("NetIncomeCommonStockholders")
    eps_ttm_point = ttm("DilutedEPS")
    eps_ttm = eps_ttm_point.value if eps_ttm_point else _div(ni_ttm.value if ni_ttm else None, shares)
    cfo = ttm("OperatingCashFlow")
    cfi = ttm("InvestingCashFlow")
    cff = ttm("FinancingCashFlow")
    capex = ttm("CapitalExpenditure")
    fcf = ttm("FreeCashFlow")
    nii_ttm = ttm("NetInterestIncome")
    val = lambda p: p.value if p else None  # noqa: E731

    def shares_at(when: str) -> float | None:
        return _at(series, q("OrdinarySharesNumber"), when) or shares

    # Annualised dari tahun berjalan.
    year = date.fromisoformat(quarter_end).year if quarter_end else None
    n_ytd = _ytd_quarters(series, q("NetIncomeCommonStockholders"), year) if year else 0
    ni_ytd = _ytd(series, q("NetIncomeCommonStockholders"), year, n_ytd) if n_ytd else None
    rev_ytd = _ytd(series, q("TotalRevenue"), year, _ytd_quarters(series, q("TotalRevenue"), year)) if year else None
    n_rev_ytd = _ytd_quarters(series, q("TotalRevenue"), year) if year else 0
    ni_annualised = ni_ytd * 4 / n_ytd if ni_ytd is not None else None
    rev_annualised = rev_ytd * 4 / n_rev_ytd if rev_ytd is not None and n_rev_ytd else None
    eps_annualised = _div(ni_annualised, shares)
    annualised_basis = f"YTD {n_ytd} kuartal {year} x 4/{n_ytd}" if n_ytd else None

    equity_common = _latest(series, q("CommonStockEquity"))
    equity_total = _latest(series, q("TotalEquityGrossMinorityInterest"))
    assets = _latest(series, q("TotalAssets"))
    liabilities = _latest(series, q("TotalLiabilitiesNetMinorityInterest"))
    cash = _latest(series, q("CashAndCashEquivalents"))
    debt = _latest(series, q("TotalDebt"))
    loans = _latest(series, q("NetLoan"))
    allowance = _latest(series, q("AllowanceForLoansAndLeaseLosses"))
    deposits = _latest(series, q("TotalDeposits"))
    gross_loans = loans.value + allowance.value if loans and allowance else None
    bvps = _div(val(equity_common), shares_at(equity_common.when) if equity_common else None)

    avg_assets, assets_basis = _average_balance(series, q("TotalAssets"), assets)
    avg_equity, equity_basis = _average_balance(series, q("CommonStockEquity"), equity_common)
    pretax_q = _at(series, q("PretaxIncome"), quarter_end) if quarter_end else None
    rev_at_end = _at(series, q("TotalRevenue"), quarter_end) if quarter_end else None
    ni_at_end = _at(series, q("NetIncomeCommonStockholders"), quarter_end) if quarter_end else None

    today = today or (datetime.now(timezone.utc) + timedelta(hours=7)).date()
    div = _dividend_view(dividends or [], detail, stats, calendar, today)
    dividend_ttm = div["ttm"]
    pay_date = _epoch_date(calendar.get("dividendDate"))
    forward_eps = stats.get("forwardEps")
    qlabel = _quarter_label(quarter_end) if quarter_end else None

    sections = [
        {
            "id": "valuation",
            "title": "Valuasi",
            "items": [
                item("market_cap", "Market cap", market_cap, "idr", "harga x saham beredar"),
                item("pe_ttm", "PE (TTM)", _positive_multiple(price, eps_ttm), "x"),
                item("pe_annualised", "PE (annualised)", _positive_multiple(price, eps_annualised), "x", annualised_basis),
                item("pe_forward", "Forward PE", _positive_multiple(price, forward_eps), "x", "EPS konsensus analis"),
                item("ps_ttm", "Price to sales (TTM)", _positive_multiple(market_cap, val(rev_ttm)), "x"),
                item("pbv", "Price to book value", _positive_multiple(price, bvps), "x", qlabel),
                item("pcf_ttm", "Price to cash flow (TTM)", _positive_multiple(market_cap, val(cfo)), "x",
                     hint="Tidak dihitung: arus kas operasi TTM negatif" if val(cfo) is not None and val(cfo) <= 0 else None),
                item("pfcf_ttm", "Price to free cash flow (TTM)", _positive_multiple(market_cap, val(fcf)), "x",
                     hint="Tidak dihitung: free cash flow TTM negatif" if val(fcf) is not None and val(fcf) <= 0 else None),
            ],
        },
        {
            "id": "per_share",
            "title": "Per saham",
            "items": [
                item("eps_ttm", "EPS (TTM)", eps_ttm, "price"),
                item("eps_annualised", "EPS (annualised)", eps_annualised, "price", annualised_basis),
                item("revenue_per_share", "Revenue per share (TTM)", _div(val(rev_ttm), shares), "price"),
                item("cash_per_share", "Cash per share", _div(val(cash), shares_at(cash.when) if cash else None), "price", qlabel),
                item("bvps", "Book value per share", bvps, "price", qlabel),
                item("fcf_per_share", "Free cash flow per share (TTM)", _div(val(fcf), shares), "price"),
            ],
        },
        {
            "id": "profitability",
            "title": "Profitabilitas",
            "items": [
                item("roa_ttm", "Return on assets (TTM)", _pct(_div(val(ni_ttm), avg_assets)), "pct", assets_basis),
                item("roe_ttm", "Return on equity (TTM)", _pct(_div(val(ni_ttm), avg_equity)), "pct", equity_basis),
                item("net_margin_q", "Net profit margin", _pct(_div(ni_at_end, rev_at_end)), "pct", qlabel),
                item("pretax_margin_q", "Pretax margin", _pct(_div(pretax_q, rev_at_end)), "pct", qlabel,
                     "Pengganti operating margin: Yahoo tidak memisahkan laba operasi bank"),
                item("nii_ttm", "Net interest income (TTM)", val(nii_ttm), "idr"),
            ],
        },
        {
            "id": "bank",
            "title": "Neraca dan rasio bank",
            "items": [
                item("ldr", "Loan to deposit ratio", _pct(_div(val(loans), val(deposits))), "pct", qlabel,
                     "Kredit bersih (setelah cadangan) dibagi dana pihak ketiga. LDR resmi OJK memakai kredit bruto."),
                item("loan_loss_reserve", "Cadangan kerugian kredit", _pct(_div(val(allowance), gross_loans)), "pct", qlabel,
                     "Cadangan dibagi kredit bruto. Bukan NPL coverage, karena nilai NPL tidak tersedia."),
                item("der", "Debt to equity", _div(val(debt), val(equity_total)), "x", qlabel,
                     "Pinjaman dan surat utang saja; simpanan nasabah tidak dihitung sebagai utang"),
                item("cash", "Cash", val(cash), "idr", qlabel),
                item("total_assets", "Total aset", val(assets), "idr", qlabel),
                item("total_liabilities", "Total liabilitas", val(liabilities), "idr", qlabel),
                item("common_equity", "Ekuitas pemilik entitas induk", val(equity_common), "idr", qlabel),
                item("total_equity", "Total ekuitas", val(equity_total), "idr", qlabel, "Termasuk kepentingan nonpengendali"),
            ],
        },
        {
            "id": "cashflow",
            "title": "Arus kas (TTM)",
            "items": [
                item("cfo_ttm", "Cash from operations", val(cfo), "idr"),
                item("cfi_ttm", "Cash from investing", val(cfi), "idr"),
                item("cff_ttm", "Cash from financing", val(cff), "idr"),
                item("capex_ttm", "Capital expenditure", val(capex), "idr"),
                item("fcf_ttm", "Free cash flow", val(fcf), "idr"),
            ],
        },
        {
            "id": "dividend",
            "title": "Dividen",
            "items": [
                item("dividend_ttm", "Dividen per saham (TTM)", dividend_ttm, "price", "ex date 12 bulan terakhir"),
                item("dividend_yield", "Dividend yield (TTM)", _pct(_div(dividend_ttm, price)), "pct"),
                item("payout_ratio", "Payout ratio", _pct(_positive_multiple(dividend_ttm, eps_ttm)), "pct", "dividen TTM / EPS TTM"),
                item("last_dividend", "Dividen terakhir per saham", div["last"][1] if div["last"] else None, "price"),
                item("ex_date", "Ex date terakhir", div["last"][0] if div["last"] else None, "date"),
                *([item("next_dividend", "Dividen terjadwal per saham", div["upcoming"][1], "price"),
                   item("next_ex_date", "Ex date berikutnya", div["upcoming"][0], "date")] if div["upcoming"] else []),
                *([item("pay_date", "Pay date", pay_date, "date")] if pay_date else []),
            ],
        },
        {
            "id": "shares",
            "title": "Saham",
            "items": [
                item("shares_outstanding", "Saham beredar", shares, "shares"),
                item("free_float", "Free float", _pct(_div(float_shares, shares)), "pct",
                     "Saham di luar pemegang saham pengendali dan orang dalam, menurut Yahoo"),
            ],
        },
    ]

    return {
        "price": price,
        "price_time": _epoch_iso(price_mod.get("regularMarketTime")),
        "currency": price_mod.get("currency") or "IDR",
        "quarter_end": quarter_end,
        "quarter_label": qlabel,
        "sections": sections,
        "periods": _periods(series, shares, year, n_ytd, ni_annualised, rev_annualised, eps_annualised,
                            rev_ttm, ni_ttm, eps_ttm),
        "growth": _growth_table(series, shares_at, quarter_end),
        "dividend_history": div["history"],
        "unavailable": [{"metrics": m, "reason": r} for m, r in UNAVAILABLE],
    }


def _pct(ratio: float | None) -> float | None:
    return None if ratio is None else ratio * 100


def _epoch_iso(value) -> str | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _periods(series, shares, year, n_ytd, ni_ann, rev_ann, eps_ann, rev_ttm, ni_ttm, eps_ttm) -> dict:
    """Tabel per periode: kuartal yang tersedia, annualised, TTM, dan tahun buku terakhir."""
    rev = dict(series.get("quarterlyTotalRevenue", []))
    ni = dict(series.get("quarterlyNetIncomeCommonStockholders", []))
    shares_q = dict(series.get("quarterlyOrdinarySharesNumber", []))
    columns = []
    for when in sorted(set(rev) | set(ni)):
        n = ni.get(when)
        columns.append({
            "label": _quarter_label(when),
            "kind": "quarter",
            "end": when,
            "revenue": rev.get(when),
            "net_income": n,
            "eps": _div(n, shares_q.get(when) or shares),
        })
    if n_ytd:
        columns.append({"label": f"Annualised {year}", "kind": "annualised", "end": None,
                        "revenue": rev_ann, "net_income": ni_ann, "eps": eps_ann})
    columns.append({"label": "TTM", "kind": "ttm", "end": rev_ttm.when if rev_ttm else None,
                    "revenue": rev_ttm.value if rev_ttm else None,
                    "net_income": ni_ttm.value if ni_ttm else None, "eps": eps_ttm})
    annual_rev = _latest(series, "annualTotalRevenue")
    annual_ni = _latest(series, "annualNetIncomeCommonStockholders")
    annual_eps = _latest(series, "annualDilutedEPS")
    if annual_rev or annual_ni:
        when = (annual_rev or annual_ni).when
        columns.append({"label": f"FY {when[:4]}", "kind": "annual", "end": when,
                        "revenue": annual_rev.value if annual_rev else None,
                        "net_income": annual_ni.value if annual_ni else None,
                        "eps": annual_eps.value if annual_eps else None})
    return {"columns": columns}


def _growth_table(series: Series, shares_at, quarter_end: str | None) -> list[dict]:
    """Pertumbuhan YoY per kuartal, YTD, dan tahunan untuk revenue, laba, dan EPS."""
    rows = []
    year = date.fromisoformat(quarter_end).year if quarter_end else None

    def eps_series() -> Series:
        ni = series.get("quarterlyNetIncomeCommonStockholders", [])
        return {"quarterlyEPS": [(d, v / s) for d, v in ni if (s := shares_at(d))]}

    eps_q = eps_series()
    specs = [
        ("revenue", "Revenue", series, "quarterlyTotalRevenue", "annualTotalRevenue"),
        ("net_income", "Laba bersih", series, "quarterlyNetIncomeCommonStockholders", "annualNetIncomeCommonStockholders"),
        ("eps", "EPS", eps_q, "quarterlyEPS", "annualDilutedEPS"),
    ]
    for key, label, source, qname, aname in specs:
        quarter = quarter_yoy = ytd = ytd_yoy = None
        if quarter_end:
            quarter = _at(source, qname, quarter_end)
            quarter_yoy = _growth(quarter, _at(source, qname, _year_ago(quarter_end)))
            n = _ytd_quarters(source, qname, year)
            if n:
                ytd = _ytd(source, qname, year, n)
                ytd_yoy = _growth(ytd, _ytd(source, qname, year - 1, n))
        annual = _points(series, aname)
        annual_value = annual[-1].value if annual else None
        annual_yoy = _growth(annual[-1].value, annual[-2].value) if len(annual) >= 2 else None
        rows.append({
            "key": key,
            "label": label,
            "unit": "price" if key == "eps" else "idr",
            "quarter": quarter,
            "quarter_yoy": quarter_yoy,
            "ytd": ytd,
            "ytd_yoy": ytd_yoy,
            "annual": annual_value,
            "annual_label": f"FY {annual[-1].when[:4]}" if annual else None,
            "annual_yoy": annual_yoy,
        })
    return rows
