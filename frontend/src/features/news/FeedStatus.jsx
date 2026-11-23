import { fmtWib, fmtWibTime } from '../../lib/format.js';

function describe(feed, syncing) {
  if (syncing) return { tone: 'syncing', text: 'Sedang memeriksa berita baru' };
  if (feed.status === 'ok') {
    const counts = feed.last_new_count ? ` · ${feed.last_new_count} artikel relevan baru` : '';
    return { tone: 'ok', text: `Diperiksa ${fmtWibTime(feed.last_success_at)}${counts}` };
  }
  if (feed.status === 'error') {
    const last = feed.last_success_at ? `Terakhir berhasil ${fmtWib(feed.last_success_at)}.` : 'Belum pernah berhasil.';
    return { tone: 'error', text: `Gagal ${fmtWibTime(feed.last_attempt_at)}: ${feed.last_error}. ${last}` };
  }
  return { tone: 'pending', text: 'Menunggu putaran pertama' };
}

const MODEL_TEXT = {
  ready: { tone: 'ok', text: 'siap menilai sentimen per emiten' },
  loading: { tone: 'syncing', text: 'sedang dimuat. Artikel baru dinilai begitu model siap.' },
  pending: { tone: 'pending', text: 'menunggu dimuat' },
  disabled: { tone: 'pending', text: 'dimatikan (SENTIMENT_ENABLED=0). Artikel tampil sebagai Belum dinilai.' },
};

function ModelStatus({ model }) {
  const info =
    model.status === 'error'
      ? { tone: 'error', text: `gagal dimuat: ${model.error}. Artikel tampil sebagai Belum dinilai.` }
      : MODEL_TEXT[model.status];
  return (
    <div className="feeds__item feeds__item--model">
      <span className={`status-dot status-dot--${info.tone}`} aria-hidden="true" />
      <div>
        <p className="feeds__name">Model sentimen IndoBERT</p>
        <p className="feeds__text">
          <code>{model.id}</code> {info.text}
        </p>
      </div>
    </div>
  );
}

export default function FeedStatus({ state, syncing, onSync }) {
  const { data, error, loading } = state;
  const minutes = data ? Math.round(data.interval_seconds / 60) : null;

  return (
    <section className="panel feeds" aria-labelledby="feeds-title">
      <h2 id="feeds-title" className="panel__title">
        Sumber berita live
      </h2>

      {loading && !data && <p className="empty-note">Memuat status sumber.</p>}
      {error && !data && (
        <p className="note note--error" role="alert">
          Status sumber tidak dapat dimuat: {error}
        </p>
      )}

      {data && (
        <>
          <ModelStatus model={data.model} />
          <ul className="feeds__list" aria-live="polite">
            {data.feeds.map((feed) => {
              const info = describe(feed, syncing);
              return (
                <li key={feed.id} className="feeds__item">
                  <span className={`status-dot status-dot--${info.tone}`} aria-hidden="true" />
                  <div>
                    <p className="feeds__name">{feed.name}</p>
                    <p className="feeds__text">{info.text}</p>
                  </div>
                </li>
              );
            })}
          </ul>
        </>
      )}

      <div className="feeds__foot">
        <p className="feeds__schedule">
          {data?.auto_sync
            ? `Dicek otomatis tiap ${minutes} menit lewat news sitemap. Berita ${data.retention_days} hari terakhir disimpan di memori dan hilang saat server berhenti.`
            : 'Pemantauan otomatis dimatikan (NEWS_SYNC_ENABLED=0).'}
        </p>
        {/* Satu-satunya tombol berwarna hangat di layar: aksi utama skenario demo. */}
        <button type="button" className="btn-cta" onClick={onSync} disabled={syncing || !data}>
          {syncing ? 'Memeriksa…' : 'Cek berita sekarang'}
        </button>
      </div>
    </section>
  );
}
