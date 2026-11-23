import { useEffect, useState } from 'react';
import { PRESETS } from './range.js';

export default function RangeControls({ range, effective, bounds, onChange }) {
  const [draft, setDraft] = useState(effective);

  // Isi input mengikuti rentang efektif saat preset atau emiten berganti.
  useEffect(() => setDraft(effective), [effective.start, effective.end]);

  const invalid = draft.start && draft.end && draft.start > draft.end;

  const commit = (next) => {
    setDraft(next);
    if (next.start && next.end && next.start <= next.end) {
      onChange({ preset: 'custom', start: next.start, end: next.end });
    }
  };

  return (
    <div className="range">
      <fieldset className="range__presets">
        <legend className="visually-hidden">Rentang cepat</legend>
        {PRESETS.map((preset) => (
          <label key={preset.id} className="chip" title={preset.title}>
            <input
              type="radio"
              name="range-preset"
              value={preset.id}
              checked={range.preset === preset.id}
              onChange={() => onChange({ preset: preset.id })}
            />
            <span>{preset.label}</span>
          </label>
        ))}
      </fieldset>

      <div className="range__dates">
        <label className="field">
          <span className="field__label">Dari</span>
          <input
            type="date"
            value={draft.start ?? ''}
            min={bounds.first ?? undefined}
            max={bounds.last ?? undefined}
            aria-invalid={invalid || undefined}
            aria-describedby={invalid ? 'range-error' : undefined}
            onChange={(e) => commit({ ...draft, start: e.target.value })}
          />
        </label>
        <label className="field">
          <span className="field__label">Sampai</span>
          <input
            type="date"
            value={draft.end ?? ''}
            min={bounds.first ?? undefined}
            max={bounds.last ?? undefined}
            aria-invalid={invalid || undefined}
            aria-describedby={invalid ? 'range-error' : undefined}
            onChange={(e) => commit({ ...draft, end: e.target.value })}
          />
        </label>
      </div>
      {invalid && (
        <p id="range-error" className="range__error" role="alert">
          Tanggal awal harus sebelum tanggal akhir. Chart masih menampilkan rentang sebelumnya.
        </p>
      )}
    </div>
  );
}
