export default function TickerSwitcher({ tickers, value, onChange }) {
  const index = Math.max(0, tickers.findIndex((t) => t.code === value));
  return (
    <fieldset className="ticker-switch" style={{ '--count': tickers.length, '--index': index }}>
      <legend className="visually-hidden">Pilih emiten</legend>
      <span className="ticker-switch__thumb" aria-hidden="true" />
      {tickers.map((ticker) => (
        <label key={ticker.code} className="ticker-switch__option">
          <input
            type="radio"
            name="ticker"
            value={ticker.code}
            checked={ticker.code === value}
            onChange={() => onChange(ticker.code)}
          />
          <span className="ticker-switch__code">{ticker.code}</span>
          <span className="ticker-switch__name">{ticker.short_name}</span>
        </label>
      ))}
    </fieldset>
  );
}
