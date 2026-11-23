import { fmtDateLong, fmtInt, fmtPct, fmtPrice } from '../../lib/format.js';

function Row({ label, value, hint, tone }) {
  return (
    <div className="detail__row">
      <dt>{label}</dt>
      <dd className={tone ? `tone-${tone}` : undefined}>
        {value}
        {hint && <span className="detail__hint">{hint}</span>}
      </dd>
    </div>
  );
}

export default function CandleDetail({ candle, previous, onClear }) {
  if (!candle) {
    return (
      <section className="panel detail" aria-labelledby="detail-title">
        <h2 id="detail-title" className="panel__title">Detail sesi</h2>
        <p className="empty-note">
          Klik satu candle untuk melihat OHLC, volume, dan nilai ketiga band. Dengan keyboard, fokuskan chart lalu
          tekan panah kiri atau kanan.
        </p>
      </section>
    );
  }

  const change = previous ? candle.close - previous.close : null;
  const changePct = previous ? (change / previous.close) * 100 : null;
  const hasBand = candle.bb_middle != null;

  return (
    <section className="panel detail" aria-labelledby="detail-title">
      <div className="panel__head">
        <h2 id="detail-title" className="panel__title">
          Sesi {fmtDateLong(candle.date)}
        </h2>
        <button type="button" className="btn-ghost" onClick={onClear}>
          Hapus pilihan
        </button>
      </div>

      {/* key memicu animasi sorot singkat setiap kali sesi berganti */}
      <div key={candle.date} className="detail__grid">
        <dl className="detail__list">
          <Row label="Open" value={fmtPrice(candle.open)} />
          <Row label="High" value={fmtPrice(candle.high)} />
          <Row label="Low" value={fmtPrice(candle.low)} />
          <Row
            label="Close"
            value={fmtPrice(candle.close)}
            hint={change == null ? null : `${change >= 0 ? '+' : ''}${fmtPrice(change)} (${fmtPct(changePct)})`}
            tone={change == null || change === 0 ? null : change > 0 ? 'up' : 'down'}
          />
          <Row label="Volume" value={fmtInt(candle.volume)} hint="lembar" />
        </dl>
        <div className="detail__band">
          <dl className="detail__list">
            <Row label="Band atas" value={fmtPrice(candle.bb_upper)} />
            <Row label="SMA 20" value={fmtPrice(candle.bb_middle)} />
            <Row label="Band bawah" value={fmtPrice(candle.bb_lower)} />
          </dl>
          <p className="detail__note">
            {hasBand
              ? 'Close, SMA 20 sesi, ±2 standar deviasi sampel. Dihitung dari histori penuh, jadi tidak berubah saat rentang diganti.'
              : 'Band kosong karena belum ada 20 sesi penutupan sebelum tanggal ini.'}
          </p>
        </div>
      </div>
    </section>
  );
}
