import { useMemo } from 'react';

const WIDTH = 1000;
const HEIGHT = 120;
const TOP_PAD = 14;

/**
 * Motif identitas: garis punggung gunung dari Desain.md digambar dari harga penutupan
 * seluruh histori emiten aktif. Bentuknya data asli, bukan dekorasi.
 */
export default function Horizon({ code, values }) {
  const paths = useMemo(() => {
    if (!values || values.length < 2) return null;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;
    const step = WIDTH / (values.length - 1);
    const points = values.map((value, index) => {
      const x = index * step;
      const y = TOP_PAD + (1 - (value - min) / span) * (HEIGHT - TOP_PAD - 8);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });
    const line = `M${points.join(' L')}`;
    return { line, area: `${line} L${WIDTH},${HEIGHT} L0,${HEIGHT} Z` };
  }, [values]);

  if (!paths) return <div className="horizon horizon--empty" aria-hidden="true" />;

  return (
    <svg
      key={code}
      className="horizon"
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      preserveAspectRatio="none"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id="alpine" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="rgb(2,229,239)" />
          <stop offset="71.5%" stopColor="rgb(72,89,235)" />
          <stop offset="100%" stopColor="rgb(138,56,244)" />
        </linearGradient>
        <linearGradient id="alpine-fade" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#fff" stopOpacity="0.55" />
          <stop offset="100%" stopColor="#fff" stopOpacity="0" />
        </linearGradient>
        <mask id="alpine-mask">
          <rect width={WIDTH} height={HEIGHT} fill="url(#alpine-fade)" />
        </mask>
      </defs>
      <path className="horizon__area" d={paths.area} fill="url(#alpine)" mask="url(#alpine-mask)" />
      <path className="horizon__ridge" d={paths.line} pathLength="1" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
