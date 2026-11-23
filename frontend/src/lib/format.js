const priceFmt = new Intl.NumberFormat('id-ID', { maximumFractionDigits: 2 });
const intFmt = new Intl.NumberFormat('id-ID');
const pctFmt = new Intl.NumberFormat('id-ID', {
  maximumFractionDigits: 2,
  minimumFractionDigits: 2,
  signDisplay: 'exceptZero',
});
const compactFmt = new Intl.NumberFormat('id-ID', { notation: 'compact', maximumFractionDigits: 1 });

const dateLong = new Intl.DateTimeFormat('id-ID', {
  weekday: 'long',
  day: 'numeric',
  month: 'long',
  year: 'numeric',
  timeZone: 'UTC',
});
const dateShort = new Intl.DateTimeFormat('id-ID', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  timeZone: 'UTC',
});
const wibDateTime = new Intl.DateTimeFormat('id-ID', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  timeZone: 'Asia/Jakarta',
});
const wibTime = new Intl.DateTimeFormat('id-ID', {
  hour: '2-digit',
  minute: '2-digit',
  timeZone: 'Asia/Jakarta',
});

const isoToUtcDate = (iso) => new Date(`${iso}T00:00:00Z`);

export const fmtPrice = (value) => (value == null ? 'Belum tersedia' : priceFmt.format(value));
export const fmtInt = (value) => (value == null ? 'Belum tersedia' : intFmt.format(value));
export const fmtCompact = (value) => compactFmt.format(value);
export const fmtPct = (value) => `${pctFmt.format(value)}%`;
export const fmtDateLong = (iso) => dateLong.format(isoToUtcDate(iso));
export const fmtDateShort = (iso) => (iso ? dateShort.format(isoToUtcDate(iso)) : 'Belum ada');
export const fmtWib = (isoDateTime) =>
  isoDateTime ? `${wibDateTime.format(new Date(isoDateTime))} WIB` : 'Belum ada';
export const fmtWibTime = (isoDateTime) =>
  isoDateTime ? `${wibTime.format(new Date(isoDateTime))} WIB` : 'Belum ada';

const ratioFmt = new Intl.NumberFormat('id-ID', { maximumFractionDigits: 2, minimumFractionDigits: 2 });
const SCALES = [
  [1e12, 'T'],
  [1e9, 'M'],
  [1e6, 'Jt'],
];

/** Nominal besar dalam skala Indonesia: T = triliun, M = miliar, Jt = juta. */
export function fmtScaled(value) {
  const abs = Math.abs(value);
  for (const [size, suffix] of SCALES) {
    if (abs >= size) return `${ratioFmt.format(value / size)} ${suffix}`;
  }
  return priceFmt.format(value);
}

/**
 * Format nilai fundamental sesuai satuannya. null dikembalikan apa adanya.
 * bare: tanpa awalan "Rp", untuk tabel yang sudah menyebut satuannya sekali.
 */
export function fmtMetric(value, unit, { bare = false } = {}) {
  if (value == null) return null;
  const rp = bare ? '' : 'Rp ';
  switch (unit) {
    case 'idr':
      return `${rp}${fmtScaled(value)}`;
    case 'price':
      return `${rp}${priceFmt.format(value)}`;
    case 'x':
      return `${ratioFmt.format(value)}x`;
    case 'pct':
      return `${ratioFmt.format(value)}%`;
    case 'shares':
      return `${fmtScaled(value)} lembar`;
    case 'date':
      return fmtDateShort(value);
    default:
      return String(value);
  }
}
