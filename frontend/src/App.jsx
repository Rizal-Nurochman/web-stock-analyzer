import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from './lib/api.js';
import { fmtDateShort, fmtPct, fmtPrice } from './lib/format.js';
import Horizon from './features/market/Horizon.jsx';
import TickerSwitcher from './features/market/TickerSwitcher.jsx';
import RangeControls from './features/market/RangeControls.jsx';
import PriceChart from './features/market/PriceChart.jsx';
import CandleDetail from './features/market/CandleDetail.jsx';
import { DEFAULT_RANGE, resolveRange } from './features/market/range.js';
import NewsPanel from './features/news/NewsPanel.jsx';
import FeedStatus from './features/news/FeedStatus.jsx';
import PriceSource from './features/market/PriceSource.jsx';
import FundamentalPanel from './features/fundamental/FundamentalPanel.jsx';

const idle = { loading: true, error: null, data: null };

/** Pantau status sinkronisasi berkala; panggil onFinished saat putaran baru selesai. */
function usePolledStatus(load, onFinished) {
  const [state, setState] = useState(idle);
  const lastRun = useRef(null);
  const finished = useRef(onFinished);
  finished.current = onFinished;
  useEffect(() => {
    let cancelled = false;
    let timer;
    const poll = async () => {
      try {
        const data = await load();
        if (cancelled) return;
        setState({ loading: false, error: null, data });
        if (lastRun.current && data.last_run_finished_at !== lastRun.current) finished.current();
        lastRun.current = data.last_run_finished_at;
        timer = setTimeout(poll, data.syncing ? 3000 : 20000);
      } catch (error) {
        if (cancelled) return;
        setState((prev) => ({ ...prev, loading: false, error: error.message }));
        timer = setTimeout(poll, 20000);
      }
    };
    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [load]);
  const accept = useCallback((data) => {
    lastRun.current = data.last_run_finished_at;
    setState({ loading: false, error: null, data });
  }, []);
  return [state, accept];
}

/** Ambil data dan abaikan respons lama ketika parameter sudah berubah. */
function useResource(loader, deps, enabled = true) {
  const [state, setState] = useState(idle);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    if (!enabled) return undefined;
    const controller = new AbortController();
    setState((prev) => ({ ...prev, loading: true, error: null }));
    loader(controller.signal)
      .then((data) => setState({ loading: false, error: null, data }))
      .catch((error) => {
        if (error.name === 'AbortError') return;
        setState((prev) => ({ ...prev, loading: false, error: error.message }));
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, reload, enabled]);
  const retry = useCallback(() => setReload((n) => n + 1), []);
  return [state, retry];
}

export default function App() {
  const [ticker, setTicker] = useState('BBCA');
  const [range, setRange] = useState(DEFAULT_RANGE);
  const [selectedDate, setSelectedDate] = useState(null);
  const [newsMode, setNewsMode] = useState('latest');
  const [newsTick, setNewsTick] = useState(0);
  const [manualSync, setManualSync] = useState(false);
  const [syncError, setSyncError] = useState(null);
  const [manualPriceSync, setManualPriceSync] = useState(false);
  const [priceSyncError, setPriceSyncError] = useState(null);

  const [tickersState, retryTickers] = useResource((signal) => api.tickers(signal), []);
  const tickers = tickersState.data ?? [];
  const info = tickers.find((t) => t.code === ticker);
  const hasPrices = tickers.some((t) => t.rows > 0);

  const effective = useMemo(
    () => resolveRange(range, info?.first_date, info?.last_date),
    [range, info?.first_date, info?.last_date],
  );

  const [marketState, retryMarket] = useResource(
    (signal) => api.market(ticker, effective.start, effective.end, signal),
    [ticker, effective.start, effective.end],
    Boolean(info?.last_date),
  );
  const candles = marketState.data?.ticker === ticker ? marketState.data.candles : [];

  const sessionDate = newsMode === 'session' ? selectedDate : null;
  const [newsState, retryNews] = useResource(
    (signal) => api.news(ticker, sessionDate, signal),
    [ticker, sessionDate, newsTick],
  );

  // Pergantian emiten mengosongkan sesi terpilih (R-01).
  const changeTicker = (code) => {
    if (code === ticker) return;
    setTicker(code);
    setSelectedDate(null);
    setNewsMode('latest');
  };

  const selectCandle = useCallback((date) => {
    setSelectedDate(date);
    setNewsMode(date ? 'session' : 'latest');
  }, []);

  // Sesi terpilih yang keluar dari rentang baru tidak lagi bisa ditunjuk di chart.
  useEffect(() => {
    if (!selectedDate || marketState.loading || marketState.data?.ticker !== ticker) return;
    if (!marketState.data.candles.some((c) => c.date === selectedDate)) selectCandle(null);
  }, [marketState, selectedDate, ticker, selectCandle]);

  const selectedIndex = candles.findIndex((c) => c.date === selectedDate);
  const selected = selectedIndex >= 0 ? candles[selectedIndex] : null;
  const previous = selectedIndex > 0 ? candles[selectedIndex - 1] : null;

  // Status feed dan harga dipantau berkala. Saat putaran selesai, data terkait dimuat ulang.
  const [feeds, acceptFeeds] = usePolledStatus(api.feeds, () => setNewsTick((n) => n + 1));
  const reloadPrices = () => {
    retryTickers();
    retryMarket();
  };
  const [prices, acceptPrices] = usePolledStatus(api.prices, reloadPrices);
  const syncing = manualSync || Boolean(feeds.data?.syncing);
  const pricesSyncing = manualPriceSync || Boolean(prices.data?.syncing);

  const syncPricesNow = async () => {
    setManualPriceSync(true);
    setPriceSyncError(null);
    try {
      acceptPrices(await api.syncPrices());
      reloadPrices();
    } catch (error) {
      setPriceSyncError(error.message);
    } finally {
      setManualPriceSync(false);
    }
  };

  const syncNow = async () => {
    setManualSync(true);
    setSyncError(null);
    try {
      const data = await api.syncNow();
      acceptFeeds(data);
      setNewsTick((n) => n + 1);
    } catch (error) {
      setSyncError(error.message);
    } finally {
      setManualSync(false);
    }
  };

  const change = info?.last_close != null && info?.prev_close ? info.last_close - info.prev_close : null;

  return (
    <>
      <a className="skip-link" href="#chart-title">
        Langsung ke chart
      </a>
      <header className="topbar">
        <p className="wordmark">Web Stock Analyzer</p>
        <p className="topbar__meta">Demo lokal · harga dan fundamental dari Yahoo Finance, berita dari sitemap portal</p>
      </header>

      <main>
        <section className="summit" aria-labelledby="ticker-heading">
          <Horizon code={ticker} values={info?.sparkline} />
          <div className="summit__inner">
            <div className="summit__title" key={ticker}>
              <h1 id="ticker-heading">
                <span className="summit__code">{ticker}</span>
                <span className="summit__name">{info?.name ?? 'Memuat emiten'}</span>
              </h1>
              {info?.last_close != null && (
                <p className="summit__price">
                  <span className="summit__close">{fmtPrice(info.last_close)}</span>
                  {change != null && (
                    <span className={change > 0 ? 'tone-up' : change < 0 ? 'tone-down' : undefined}>
                      {change > 0 ? '+' : ''}
                      {fmtPrice(change)} ({fmtPct((change / info.prev_close) * 100)})
                    </span>
                  )}
                  <span className="summit__asof">Close {fmtDateShort(info.last_date)}</span>
                </p>
              )}
            </div>
            {tickers.length > 0 && <TickerSwitcher tickers={tickers} value={ticker} onChange={changeTicker} />}
          </div>
        </section>

        {tickersState.error && !tickersState.data && (
          <div className="page-state note note--error" role="alert">
            <p className="note__title">Daftar emiten gagal dimuat</p>
            <p className="note__body">{tickersState.error}</p>
            <button type="button" className="btn-ghost" onClick={retryTickers}>
              Coba hubungi server lagi
            </button>
          </div>
        )}

        {tickersState.data && !hasPrices && (
          <div className="page-state note note--unavailable">
            <p className="note__title">Belum ada data harga di database</p>
            <p className="note__body">
              Histori diambil otomatis dari Yahoo Finance saat server berjalan dan internet tersedia. Tekan{' '}
              <strong>Perbarui harga</strong> untuk mencoba sekarang, atau impor CSV cadangan:{' '}
              <code>python -m app.market.importer data/BBCA_BBRI_BMRI_BBNI_combined.csv</code>.
            </p>
          </div>
        )}

        <div className="workspace">
          <div className="workspace__main">
            <section className="panel chart-panel" aria-labelledby="chart-title">
              <div className="panel__head">
                <h2 id="chart-title" className="panel__title" tabIndex={-1}>
                  Candle harian, Bollinger Bands, dan volume
                </h2>
                <p className="chart-panel__asof">
                  Harga terakhir tersedia <strong>{fmtDateShort(info?.last_date)}</strong>
                </p>
              </div>

              <PriceSource
                ticker={ticker}
                source={info?.source}
                state={prices}
                syncing={pricesSyncing}
                error={priceSyncError}
                onSync={syncPricesNow}
              />

              <RangeControls
                range={range}
                effective={effective}
                bounds={{ first: info?.first_date, last: info?.last_date }}
                onChange={setRange}
              />

              <div className="chart-stage">
                <PriceChart
                  candles={candles}
                  dataKey={`${ticker}:${effective.start}:${effective.end}`}
                  selectedDate={selectedDate}
                  onSelect={selectCandle}
                />
                <span key={ticker} className="chart-stage__sweep" aria-hidden="true" />
                {marketState.loading && info?.last_date && (
                  <div className="chart-stage__overlay" role="status">
                    <span className="spinner" aria-hidden="true" />
                    Memuat candle {ticker}
                  </div>
                )}
                {marketState.error && (
                  <div className="chart-stage__overlay chart-stage__overlay--solid" role="alert">
                    <p>Chart gagal dimuat: {marketState.error}</p>
                    <button type="button" className="btn-ghost" onClick={retryMarket}>
                      Muat ulang chart
                    </button>
                  </div>
                )}
                {!marketState.loading && !marketState.error && info?.last_date && candles.length === 0 && (
                  <div className="chart-stage__overlay chart-stage__overlay--solid">
                    <p>
                      Tidak ada sesi pada rentang ini. Data {ticker} tersedia {fmtDateShort(info.first_date)} sampai{' '}
                      {fmtDateShort(info.last_date)}.
                    </p>
                  </div>
                )}
                {tickersState.data && !info?.last_date && (
                  <div className="chart-stage__overlay chart-stage__overlay--solid">
                    <p>Belum ada histori harga untuk {ticker}.</p>
                  </div>
                )}
              </div>

              <ul className="chart-key" aria-label="Keterangan chart">
                <li><span className="key key--up" aria-hidden="true" />Close di atas Open</li>
                <li><span className="key key--down" aria-hidden="true" />Close di bawah Open</li>
                <li><span className="key key--band" aria-hidden="true" />Bollinger Bands (20, 2)</li>
                <li><span className="key key--vol" aria-hidden="true" />Volume</li>
              </ul>
            </section>

            <CandleDetail candle={selected} previous={previous} onClear={() => selectCandle(null)} />
            <FundamentalPanel ticker={ticker} />
          </div>

          <aside className="workspace__side" aria-label="Berita dan status sumber">
            <NewsPanel
              ticker={ticker}
              mode={newsMode}
              onModeChange={setNewsMode}
              selectedDate={selectedDate}
              state={newsState}
              onRetry={retryNews}
            />
            <FeedStatus state={feeds} syncing={syncing} onSync={syncNow} />
            {syncError && (
              <p className="note note--error" role="alert">
                Sinkronisasi manual gagal: {syncError}
              </p>
            )}
          </aside>
        </div>
      </main>

      <footer className="footer">
        <p>
          Harga harian dari <a href="https://finance.yahoo.com/quote/BBCA.JK/history/">Yahoo Finance</a>{' '}
          (data tidak resmi, disimpan lokal; hari libur bursa dibuang). Fundamental dari endpoint laporan keuangan
          dan ringkasan kuotasi Yahoo Finance, hanya di-cache di memori selama 6 jam. Berita live dari{' '}
          <a href="https://www.cnbcindonesia.com/">CNBC Indonesia</a>,{' '}
          <a href="https://www.kontan.co.id/">Kontan</a>, <a href="https://katadata.co.id/">Katadata</a>,{' '}
          <a href="https://money.kompas.com/">Kompas Money</a>,{' '}
          <a href="https://finance.detik.com/">detikFinance</a>,{' '}
          <a href="https://www.cnnindonesia.com/ekonomi">CNN Indonesia</a>, dan{' '}
          <a href="https://infobanknews.com/">Infobank</a>. Chart dibuat dengan{' '}
          <a href="https://www.tradingview.com/lightweight-charts/">TradingView Lightweight Charts</a>.
        </p>
        <p>
          Sentimen diprediksi model IndoBERT pada kalimat yang menyebut tiap emiten. Model dilatih pada data
          sentimen umum, bukan khusus berita keuangan, jadi hasilnya prediksi, bukan kepastian. Temuan chart bersifat
          deskriptif, bukan rekomendasi transaksi.
        </p>
      </footer>
    </>
  );
}
