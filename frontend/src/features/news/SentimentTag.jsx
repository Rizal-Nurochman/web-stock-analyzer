const LABELS = {
  positif: 'Positif',
  netral: 'Netral',
  negatif: 'Negatif',
  belum_dinilai: 'Belum dinilai',
};

const pct = new Intl.NumberFormat('id-ID', { style: 'percent', maximumFractionDigits: 0 });

export default function SentimentTag({ value, confidence }) {
  const key = LABELS[value] ? value : 'belum_dinilai';
  const showConfidence = key !== 'belum_dinilai' && confidence != null;
  return (
    <span
      className={`tag tag--${key}`}
      title={showConfidence ? `Keyakinan model ${pct.format(confidence)}` : undefined}
    >
      <span className="tag__dot" aria-hidden="true" />
      {LABELS[key]}
      {showConfidence && <span className="tag__confidence">{pct.format(confidence)}</span>}
    </span>
  );
}
