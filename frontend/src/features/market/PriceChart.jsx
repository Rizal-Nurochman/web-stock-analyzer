import { useEffect, useMemo, useRef, useState } from 'react';
import { createChart, CrosshairMode, LineStyle } from 'lightweight-charts';
import { fmtCompact, fmtDateShort, fmtPrice } from '../../lib/format.js';

// Warna fungsional dari Desain.md: biru = naik, koral = turun, violet = indikator turunan.
const COLORS = {
  up: '#3d8bff',
  down: '#ff3a63',
  band: 'rgba(132, 125, 255, 0.95)',
  bandMid: 'rgba(132, 125, 255, 0.6)',
  volUp: 'rgba(61, 139, 255, 0.35)',
  volDown: 'rgba(255, 58, 99, 0.35)',
  text: '#9b9ba4',
  line: '#292a4d',
};

function toIso(time) {
  if (!time) return null;
  if (typeof time === 'string') return time;
  if (typeof time === 'object') {
    const m = String(time.month).padStart(2, '0');
    const d = String(time.day).padStart(2, '0');
    return `${time.year}-${m}-${d}`;
  }
  return new Date(time * 1000).toISOString().slice(0, 10);
}

export default function PriceChart({ candles, dataKey, selectedDate, onSelect }) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const seriesRef = useRef({});
  const onSelectRef = useRef(onSelect);
  const [hoverDate, setHoverDate] = useState(null);

  onSelectRef.current = onSelect;

  const byDate = useMemo(() => new Map(candles.map((c, i) => [c.date, { ...c, index: i }])), [candles]);
  const byDateRef = useRef(byDate);
  byDateRef.current = byDate;

  useEffect(() => {
    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { type: 'solid', color: 'transparent' },
        textColor: COLORS.text,
        fontFamily: 'Inter, system-ui, sans-serif',
        fontSize: 11,
        // Logo dipindah ke footer sebagai tautan atribusi agar tidak menutupi bar volume.
        attributionLogo: false,
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { color: 'rgba(41, 42, 77, 0.45)' },
      },
      rightPriceScale: { borderColor: COLORS.line, scaleMargins: { top: 0.08, bottom: 0.26 } },
      timeScale: { borderColor: COLORS.line, rightOffset: 3, minBarSpacing: 0.5 },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: '#535380', labelBackgroundColor: '#2c2b52' },
        horzLine: { color: '#535380', labelBackgroundColor: '#2c2b52' },
      },
      localization: { locale: 'id-ID', priceFormatter: (p) => fmtPrice(p) },
      handleScale: { axisPressedMouseMove: true },
    });

    const volume = chart.addHistogramSeries({
      priceScaleId: 'volume',
      priceFormat: { type: 'custom', formatter: (v) => fmtCompact(v) },
      lastValueVisible: false,
      priceLineVisible: false,
    });
    chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

    const bandOptions = {
      color: COLORS.band,
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    };
    const upper = chart.addLineSeries(bandOptions);
    const lower = chart.addLineSeries(bandOptions);
    const middle = chart.addLineSeries({ ...bandOptions, color: COLORS.bandMid, lineStyle: LineStyle.Dashed });

    const candle = chart.addCandlestickSeries({
      upColor: COLORS.up,
      downColor: COLORS.down,
      wickUpColor: COLORS.up,
      wickDownColor: COLORS.down,
      borderVisible: false,
      priceLineColor: '#535380',
    });

    chart.subscribeClick((param) => {
      const iso = toIso(param.time);
      if (iso && byDateRef.current.has(iso)) onSelectRef.current(iso);
    });
    chart.subscribeCrosshairMove((param) => setHoverDate(toIso(param.time)));

    chartRef.current = chart;
    seriesRef.current = { candle, volume, upper, middle, lower };
    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    const { candle, volume, upper, middle, lower } = seriesRef.current;
    if (!candle) return;
    candle.setData(candles.map(({ date, open, high, low, close }) => ({ time: date, open, high, low, close })));
    volume.setData(
      candles.map((c) => ({ time: c.date, value: c.volume, color: c.close >= c.open ? COLORS.volUp : COLORS.volDown })),
    );
    // Sesi tanpa band (19 sesi pertama) dikirim tanpa value agar garis terputus, bukan nol.
    const bandData = (key) => candles.map((c) => (c[key] == null ? { time: c.date } : { time: c.date, value: c[key] }));
    upper.setData(bandData('bb_upper'));
    middle.setData(bandData('bb_middle'));
    lower.setData(bandData('bb_lower'));
    chartRef.current?.timeScale().fitContent();
  }, [candles, dataKey]);

  useEffect(() => {
    const { candle } = seriesRef.current;
    if (!candle) return;
    candle.setMarkers(
      selectedDate && byDate.has(selectedDate)
        ? [{ time: selectedDate, position: 'aboveBar', color: '#ffffff', shape: 'arrowDown', size: 1 }]
        : [],
    );
  }, [selectedDate, byDate]);

  const handleKey = (event) => {
    if (!candles.length) return;
    const current = selectedDate && byDate.has(selectedDate) ? byDate.get(selectedDate).index : candles.length;
    let next = null;
    if (event.key === 'ArrowLeft') next = Math.max(0, current - 1);
    else if (event.key === 'ArrowRight') next = Math.min(candles.length - 1, current + 1);
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = candles.length - 1;
    else if (event.key === 'Escape' && selectedDate) {
      event.preventDefault();
      onSelect(null);
      return;
    } else return;
    event.preventDefault();
    onSelect(candles[next].date);
    const range = chartRef.current?.timeScale().getVisibleLogicalRange();
    if (range && (next < range.from || next > range.to)) {
      const width = range.to - range.from;
      chartRef.current.timeScale().setVisibleLogicalRange({ from: next - width / 2, to: next + width / 2 });
    }
  };

  const legend = byDate.get(hoverDate) ?? byDate.get(selectedDate) ?? candles[candles.length - 1];

  return (
    <div className="chart">
      {legend && (
        <div className="chart__legend" aria-hidden="true">
          <span className="chart__legend-date">{fmtDateShort(legend.date)}</span>
          <span>O <b>{fmtPrice(legend.open)}</b></span>
          <span>H <b>{fmtPrice(legend.high)}</b></span>
          <span>L <b>{fmtPrice(legend.low)}</b></span>
          <span>C <b>{fmtPrice(legend.close)}</b></span>
          <span className="chart__legend-band">
            BB{' '}
            <b>
              {legend.bb_middle == null
                ? 'belum ada'
                : `${fmtPrice(legend.bb_lower)} / ${fmtPrice(legend.bb_middle)} / ${fmtPrice(legend.bb_upper)}`}
            </b>
          </span>
        </div>
      )}
      <div
        ref={containerRef}
        className="chart__canvas"
        tabIndex={0}
        role="group"
        aria-roledescription="chart candlestick"
        aria-label="Chart harga. Klik candle, atau tekan panah kiri dan kanan untuk memilih sesi. Escape menghapus pilihan."
        onKeyDown={handleKey}
      />
    </div>
  );
}
