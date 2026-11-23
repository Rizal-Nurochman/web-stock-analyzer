import { useEffect, useRef, useState } from 'react';
import { api } from '../../lib/api.js';
import { fmtMetric, fmtPct, fmtWib } from '../../lib/format.js';

const TABS = [
  { id: 'valuation', label: 'Valuasi', sections: ['valuation', 'per_share', 'shares'] },
  { id: 'performance', label: 'Kinerja', sections: ['profitability'], growth: true },
  { id: 'balance', label: 'Neraca & arus kas', sections: ['bank', 'cashflow'] },
  { id: 'dividend', label: 'Dividen', sections: ['dividend'], dividends: true },
];

/** Ambil fundamental per emiten. Hasil per emiten disimpan agar berganti tab emiten terasa instan. */
function useFundamentals(ticker) {
  const cache = useRef(new Map());
  const [state, setState] = useState({ loading: true, error: null, data: null });
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    const cached = cache.current.get(ticker);
    setState({ loading: !cached, error: null, data: cached ?? null });
    if (cached) return undefined;
    const controller = new AbortController();
    api
      .fundamentals(ticker, controller.signal)
      .then((data) => {
        cache.current.set(ticker, data);
        setState({ loading: false, error: null, data });
      })
      .catch((error) => {
        if (error.name === 'AbortError') return;
        setState({ loading: false, error: error.message, data: null });
      });
    return () => controller.abort();
  }, [ticker]);

  const refresh = async () => {
    setRefreshing(true);
    try {
      const data = await api.fundamentals(ticker, undefined, true);
      cache.current.set(ticker, data);
      setState({ loading: false, error: null, data });
    } catch (error) {
      setState((prev) => ({ ...prev, error: error.message }));
    } finally {
      setRefreshing(false);
    }
  };

  return [state, refresh, refreshing];
}

function Metric({ item }) {
  const text = fmtMetric(item.value, item.unit);
  return (
    <div className="detail__row">
      <dt>
        {item.label}
        {item.basis && <span className="fund__basis">{item.basis}</span>}
      </dt>
      <dd className={text == null ? 'fund__na' : undefined}>
        {text ?? 'Tidak tersedia'}
        {item.hint && <span className="detail__hint">{item.hint}</span>}
      </dd>
    </div>
  );
}

function Section({ section, wide }) {
  return (
    <div className={wide ? 'fund__group fund__group--wide' : 'fund__group'}>
      <h3 className="fund__group-title">{section.title}</h3>
      <dl className="detail__list">
        {section.items.map((item) => (
          <Metric key={item.key} item={item} />
        ))}
      </dl>
    </div>
  );
}

function Growth({ value }) {
  if (value == null) return <span className="fund__na">tidak tersedia</span>;
  return <span className={value > 0 ? 'tone-up' : value < 0 ? 'tone-down' : undefined}>{fmtPct(value)} YoY</span>;
}

function GrowthTable({ rows, quarterLabel }) {
  return (
    <div className="fund__group fund__group--wide">
      <h3 className="fund__group-title">Pertumbuhan</h3>
      <div className="fund__scroll">
        <table className="fund__table">
          <thead>
            <tr>
              <th scope="col">Metrik</th>
              <th scope="col">Kuartal {quarterLabel}</th>
              <th scope="col">YTD</th>
              <th scope="col">Tahunan {rows[0]?.annual_label ?? ''}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key}>
                <th scope="row">{row.label}</th>
                {[
                  [row.quarter, row.quarter_yoy],
                  [row.ytd, row.ytd_yoy],
                  [row.annual, row.annual_yoy],
                ].map(([value, growth], i) => (
                  <td key={i}>
                    <span className="fund__cell-value">{fmtMetric(value, row.unit, { bare: true }) ?? '–'}</span>
                    <Growth value={growth} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="detail__note">
        Nilai dalam rupiah (T = triliun). YoY membandingkan periode yang sama tahun sebelumnya. Yahoo hanya menyediakan sekitar lima kuartal terakhir,
        jadi bila kuartal pembanding tidak ada, pertumbuhannya tidak dihitung.
      </p>
    </div>
  );
}

function PeriodTable({ columns }) {
  const rows = [
    ['revenue', 'Revenue', 'idr'],
    ['net_income', 'Laba bersih', 'idr'],
    ['eps', 'EPS', 'price'],
  ];
  return (
    <div className="fund__group fund__group--wide">
      <h3 className="fund__group-title">Per periode</h3>
      <div className="fund__scroll">
        <table className="fund__table">
          <thead>
            <tr>
              <th scope="col">Metrik</th>
              {columns.map((c) => (
                <th key={c.label} scope="col" className={c.kind !== 'quarter' ? 'fund__col-derived' : undefined}>
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(([key, label, unit]) => (
              <tr key={key}>
                <th scope="row">{label}</th>
                {columns.map((c) => (
                  <td key={c.label} className={c.kind !== 'quarter' ? 'fund__col-derived' : undefined}>
                    {fmtMetric(c[key], unit, { bare: true }) ?? '–'}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="detail__note">
        Nilai dalam rupiah (T = triliun). Revenue bank menurut Yahoo adalah pendapatan bunga bersih ditambah pendapatan nonbunga. Laba dan EPS memakai laba
        yang dapat diatribusikan ke pemilik entitas induk. Annualised = total kuartal tahun berjalan x 4 / jumlah kuartal.
      </p>
    </div>
  );
}

function DividendHistory({ history }) {
  if (!history?.length) return null;
  return (
    <div className="fund__group">
      <h3 className="fund__group-title">Riwayat dividen (5 tahun)</h3>
      <div className="fund__scroll">
        <table className="fund__table">
          <thead>
            <tr>
              <th scope="col">Ex date</th>
              <th scope="col">Per saham</th>
            </tr>
          </thead>
          <tbody>
            {history.map((d) => (
              <tr key={d.ex_date}>
                <th scope="row">{fmtMetric(d.ex_date, 'date')}</th>
                <td>{fmtMetric(d.amount, 'price')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function FundamentalPanel({ ticker }) {
  const [tab, setTab] = useState('valuation');
  const [{ loading, error, data }, refresh, refreshing] = useFundamentals(ticker);
  const current = TABS.find((t) => t.id === tab);
  const ready = data && data.ticker === ticker && data.sections;
  const sections = ready ? current.sections.map((id) => data.sections.find((s) => s.id === id)).filter(Boolean) : [];

  return (
    <section className="panel fund" aria-labelledby="fund-title" aria-busy={loading || refreshing}>
      <div className="panel__head">
        <h2 id="fund-title" className="panel__title">
          Fundamental {ticker}
        </h2>
        <button type="button" className="btn-ghost" onClick={refresh} disabled={refreshing || loading}>
          {refreshing ? 'Mengambil dari Yahoo' : 'Ambil ulang'}
        </button>
      </div>

      {ready && (
        <p className="fund__meta">
          Laporan keuangan <strong>{data.quarter_label}</strong> · harga {fmtMetric(data.price, 'price')} per{' '}
          {fmtWib(data.price_time)} · diambil {fmtWib(data.fetched_at)}
        </p>
      )}

      <div className="toggle fund__tabs" role="group" aria-label="Kelompok metrik fundamental">
        {TABS.map((t) => (
          <button key={t.id} type="button" aria-pressed={t.id === tab} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>

      <div aria-live="polite">
        {loading && (
          <p className="fund__loading" role="status">
            <span className="spinner" aria-hidden="true" /> Mengambil fundamental {ticker} dari Yahoo Finance
          </p>
        )}

        {(error || data?.status === 'unavailable') && (
          <div className="note note--error" role="alert">
            <p className="note__title">Fundamental gagal diambil</p>
            <p className="note__body">{error || data.error}</p>
            <button type="button" className="btn-ghost" onClick={refresh} disabled={refreshing}>
              Coba lagi
            </button>
          </div>
        )}

        {data?.status === 'stale' && (
          <div className="note note--partial">
            <p className="note__title">Menampilkan data terakhir yang berhasil diambil</p>
            <p className="note__body">Pengambilan ulang gagal: {data.error}</p>
          </div>
        )}

        {ready && (
          <div key={`${ticker}:${tab}`} className="fund__grid">
            {sections.map((section) => (
              <Section key={section.id} section={section} wide={current.growth} />
            ))}
            {current.dividends && <DividendHistory history={data.dividend_history} />}
            {current.growth && (
              <>
                <GrowthTable rows={data.growth} quarterLabel={data.quarter_label} />
                <PeriodTable columns={data.periods.columns} />
              </>
            )}
          </div>
        )}
      </div>

      {ready && (
        <details className="fund__missing">
          <summary>Metrik yang tidak ditampilkan</summary>
          <ul>
            {data.unavailable.map((u) => (
              <li key={u.metrics}>
                <strong>{u.metrics}.</strong> {u.reason}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
