import { useMemo, useState } from 'react';

// Polaritas: dua kutub + abu-abu netral di tengah (diverging). "Belum dinilai" adalah data
// yang hilang, jadi tidak diberi hue sendiri melainkan arsiran.
const SLICES = [
  { key: 'positif', label: 'Positif' },
  { key: 'netral', label: 'Netral' },
  { key: 'negatif', label: 'Negatif' },
  { key: 'belum_dinilai', label: 'Belum dinilai' },
];

const SIZE = 120;
const C = SIZE / 2;
const R = SIZE / 2 - 2;

/** Persen bulat yang jumlahnya tepat 100 (metode sisa terbesar). */
function roundedPercents(counts, total) {
  const raw = counts.map((n) => (n / total) * 100);
  const floors = raw.map(Math.floor);
  let left = 100 - floors.reduce((a, b) => a + b, 0);
  raw
    .map((value, i) => ({ i, rest: value - floors[i] }))
    .sort((a, b) => b.rest - a.rest)
    .forEach(({ i }) => {
      if (left > 0 && counts[i] > 0) {
        floors[i] += 1;
        left -= 1;
      }
    });
  return floors;
}

function point(angle) {
  return [C + R * Math.cos(angle), C + R * Math.sin(angle)];
}

function arcPath(start, end) {
  const [x0, y0] = point(start);
  const [x1, y1] = point(end);
  const large = end - start > Math.PI ? 1 : 0;
  return `M${C},${C} L${x0.toFixed(2)},${y0.toFixed(2)} A${R},${R} 0 ${large} 1 ${x1.toFixed(2)},${y1.toFixed(2)} Z`;
}

export default function SentimentPie({ ticker, summary, scope }) {
  const [active, setActive] = useState(null);

  const slices = useMemo(() => {
    const present = SLICES.filter((s) => (summary?.[s.key] ?? 0) > 0 || s.key !== 'belum_dinilai');
    const counts = present.map((s) => summary?.[s.key] ?? 0);
    const total = counts.reduce((a, b) => a + b, 0);
    if (!total) return { total: 0, items: [] };
    const percents = roundedPercents(counts, total);
    let angle = -Math.PI / 2;
    const items = present.map((s, i) => {
      const sweep = (counts[i] / total) * Math.PI * 2;
      const item = { ...s, count: counts[i], percent: percents[i], start: angle, end: angle + sweep };
      angle += sweep;
      return item;
    });
    return { total, items };
  }, [summary]);

  if (!slices.total) return null;
  const description = slices.items.map((s) => `${s.label} ${s.percent}%`).join(', ');

  return (
    <figure className="sentiment" aria-labelledby={`sentiment-${ticker}`}>
      <figcaption id={`sentiment-${ticker}`} className="sentiment__caption">
        Sentimen {ticker}
        <span>
          {slices.total} artikel · {scope}
        </span>
      </figcaption>

      <svg
        key={ticker}
        className="sentiment__pie"
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        role="img"
        aria-label={`Komposisi sentimen ${ticker}: ${description}`}
      >
        <defs>
          <pattern id="sentiment-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="6" height="6" className="sentiment__hatch-bg" />
            <line x1="0" y1="0" x2="0" y2="6" className="sentiment__hatch-line" />
          </pattern>
        </defs>
        {slices.items
          .filter((s) => s.count > 0)
          .map((s) =>
            s.count === slices.total ? (
              <circle
                key={s.key}
                cx={C}
                cy={C}
                r={R}
                className={`sentiment__slice sentiment__slice--${s.key}`}
                onMouseEnter={() => setActive(s.key)}
                onMouseLeave={() => setActive(null)}
              >
                <title>{`${s.label}: ${s.count} artikel (${s.percent}%)`}</title>
              </circle>
            ) : (
              <path
                key={s.key}
                d={arcPath(s.start, s.end)}
                className={`sentiment__slice sentiment__slice--${s.key}${active && active !== s.key ? ' is-dimmed' : ''}`}
                onMouseEnter={() => setActive(s.key)}
                onMouseLeave={() => setActive(null)}
              >
                <title>{`${s.label}: ${s.count} artikel (${s.percent}%)`}</title>
              </path>
            ),
          )}
      </svg>

      <ul className="sentiment__legend">
        {slices.items.map((s) => (
          <li
            key={s.key}
            className={`sentiment__row${active === s.key ? ' is-active' : ''}`}
            onMouseEnter={() => setActive(s.key)}
            onMouseLeave={() => setActive(null)}
          >
            <span className={`sentiment__swatch sentiment__swatch--${s.key}`} aria-hidden="true" />
            <span className="sentiment__label">{s.label}</span>
            <span className="sentiment__percent">{s.percent}%</span>
            <span className="sentiment__count">{s.count}</span>
          </li>
        ))}
      </ul>
    </figure>
  );
}
