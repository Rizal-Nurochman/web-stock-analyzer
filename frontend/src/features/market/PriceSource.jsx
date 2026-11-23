import { fmtDateShort, fmtWib, fmtWibTime } from '../../lib/format.js';

/** Asal data harga emiten aktif dan hasil pembaruan terakhir dari Yahoo Finance. */
export default function PriceSource({ ticker, source, state, syncing, error, onSync }) {
  const status = state.data?.tickers.find((t) => t.ticker === ticker);

  let tone = 'pending';
  let text = 'Belum pernah diperbarui dari Yahoo Finance.';
  if (syncing) {
    tone = 'syncing';
    text = 'Mengambil histori terbaru dari Yahoo Finance.';
  } else if (status?.status === 'ok') {
    tone = 'ok';
    text = `Diperbarui ${fmtWibTime(status.last_success_at)}, sesi final terakhir ${fmtDateShort(status.last_session_date)}.`;
  } else if (status?.status === 'error') {
    tone = 'error';
    const kept = source ? ' Menampilkan data tersimpan.' : '';
    const last = status.last_success_at ? ` Terakhir berhasil ${fmtWib(status.last_success_at)}.` : '';
    text = `Pembaruan gagal: ${status.last_error}.${last}${kept}`;
  }

  return (
    <div className="price-source" aria-live="polite">
      <span className={`status-dot status-dot--${tone}`} aria-hidden="true" />
      <p className="price-source__text">
        <span className="price-source__label">
          {source === 'csv' ? 'Sumber: CSV lokal' : `Sumber: Yahoo Finance (${ticker}.JK)`}
        </span>{' '}
        {text}
        {error && <span className="tone-down"> Permintaan gagal: {error}.</span>}
      </p>
      <button type="button" className="btn-ghost" onClick={onSync} disabled={syncing || !state.data}>
        {syncing ? 'Memperbarui…' : 'Perbarui harga'}
      </button>
    </div>
  );
}
