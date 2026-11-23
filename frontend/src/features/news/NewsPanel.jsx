import { fmtDateShort, fmtWib } from '../../lib/format.js';
import SentimentTag from './SentimentTag.jsx';
import SentimentPie from './SentimentPie.jsx';

function Skeleton() {
  return (
    <ul className="news__list" aria-hidden="true">
      {[0, 1, 2, 3].map((i) => (
        <li key={i} className="news__item news__item--skeleton">
          <span className="skeleton skeleton--title" />
          <span className="skeleton skeleton--meta" />
        </li>
      ))}
    </ul>
  );
}

function StatusNote({ status, reason }) {
  if (!reason) return null;
  const tone = status === 'unavailable' ? 'unavailable' : status === 'partial' ? 'partial' : 'empty';
  const heading = {
    unavailable: 'Konteks belum tersedia',
    partial: 'Cakupan arsip sebagian',
    empty: 'Tidak ada artikel',
  }[tone];
  return (
    <div className={`note note--${tone}`}>
      <p className="note__title">{heading}</p>
      <p className="note__body">{reason}</p>
    </div>
  );
}

export default function NewsPanel({ ticker, mode, onModeChange, selectedDate, state, onRetry }) {
  const { loading, error, data } = state;
  const sessionMode = mode === 'session' && selectedDate;

  return (
    <section className="panel news" aria-labelledby="news-title" aria-busy={loading}>
      <div className="panel__head">
        <h2 id="news-title" className="panel__title">
          Berita {ticker}
        </h2>
        <div className="toggle" role="group" aria-label="Jenis daftar berita">
          <button type="button" aria-pressed={!sessionMode} onClick={() => onModeChange('latest')}>
            Terbaru
          </button>
          <button
            type="button"
            aria-pressed={Boolean(sessionMode)}
            disabled={!selectedDate}
            title={selectedDate ? undefined : 'Pilih candle dulu'}
            onClick={() => onModeChange('session')}
          >
            Sesi terpilih
          </button>
        </div>
      </div>

      {sessionMode && data?.window && (
        <p className="news__window">
          Jendela sesi {fmtDateShort(selectedDate)}: {fmtWib(data.window.start)} sampai {fmtWib(data.window.end)}
        </p>
      )}

      <div aria-live="polite">
        {loading && !data && <Skeleton />}

        {error && (
          <div className="note note--error" role="alert">
            <p className="note__title">Berita gagal dimuat</p>
            <p className="note__body">{error}</p>
            <button type="button" className="btn-ghost" onClick={onRetry}>
              Muat ulang berita
            </button>
          </div>
        )}

        {!error && data && (
          <>
            <StatusNote status={data.status} reason={data.reason} />
            {data.summary && data.ticker === ticker && (
              <SentimentPie
                ticker={ticker}
                summary={data.summary}
                scope={data.mode === 'session' ? `sesi ${fmtDateShort(data.session_date)}` : 'semua artikel di memori'}
              />
            )}
            {data.articles.length > 0 && (
              <ul className={`news__list${loading ? ' is-stale' : ''}`} key={`${data.ticker}-${data.mode}-${data.session_date}`}>
                {data.articles.map((article, index) => (
                  <li key={article.id} className="news__item" style={{ '--i': Math.min(index, 8) }}>
                    <a className="news__title" href={article.url} target="_blank" rel="noopener noreferrer">
                      {article.title}
                      <span className="visually-hidden"> (membuka situs {article.publisher} di tab baru)</span>
                    </a>
                    <div className="news__meta">
                      <span>{article.publisher}</span>
                      <span aria-hidden="true">·</span>
                      <time dateTime={article.published_at ?? undefined}>{fmtWib(article.published_at)}</time>
                      <SentimentTag value={article.sentiment} confidence={article.confidence} />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>

      {data?.coverage?.observed_since && (
        <p className="news__coverage">
          Dipantau live sejak {fmtWib(data.coverage.observed_since)}. Berita dan sentimen hanya ada di memori
          server, tidak disimpan ke database.
        </p>
      )}
    </section>
  );
}
