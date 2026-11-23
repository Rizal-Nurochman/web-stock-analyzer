export const PRESETS = [
  { id: '1M', label: '1B', months: 1, title: '1 bulan' },
  { id: '3M', label: '3B', months: 3, title: '3 bulan' },
  { id: '6M', label: '6B', months: 6, title: '6 bulan' },
  { id: '1Y', label: '1T', months: 12, title: '1 tahun' },
  { id: '3Y', label: '3T', months: 36, title: '3 tahun' },
  { id: 'ALL', label: 'Semua', months: null, title: 'Seluruh histori' },
];

export const DEFAULT_RANGE = { preset: '3M' };

function shiftMonths(iso, months) {
  const d = new Date(`${iso}T00:00:00Z`);
  const day = d.getUTCDate();
  d.setUTCDate(1);
  d.setUTCMonth(d.getUTCMonth() - months);
  const lastDay = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0)).getUTCDate();
  d.setUTCDate(Math.min(day, lastDay));
  return d.toISOString().slice(0, 10);
}

/** Rentang efektif. Preset dihitung dari tanggal terakhir data emiten aktif (R-02). */
export function resolveRange(range, firstDate, lastDate) {
  if (!lastDate) return { start: null, end: null };
  if (range.preset === 'custom') return { start: range.start, end: range.end };
  const preset = PRESETS.find((p) => p.id === range.preset) ?? PRESETS[1];
  if (preset.months == null) return { start: firstDate, end: lastDate };
  const start = shiftMonths(lastDate, preset.months);
  return { start: firstDate && start < firstDate ? firstDate : start, end: lastDate };
}
