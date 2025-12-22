import { useCallback, useMemo, useState } from 'react';

import {
  FeatureRow,
  BronzeBandSummary,
  getFeature,
  getBronzeBandSummary
} from '../lib/api';

type Status = 'idle' | 'loading' | 'error' | 'ready';

export default function FeaturePage() {
  const [location, setLocation] = useState('MKAB');
  const [month, setMonth] = useState('2025-11');
  const [rows, setRows] = useState<FeatureRow[]>([]);
  const [status, setStatus] = useState<Status>('idle');
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<BronzeBandSummary | null>(null);
  const [summaryStatus, setSummaryStatus] = useState<Status>('idle');

  const loadFeature = useCallback(() => {
    setStatus('loading');
    setError(null);
    getFeature({ location, month })
      .then((r) => {
        setRows(r);
        setStatus('ready');
      })
      .catch((err) => {
        setError(err?.message ?? 'Failed to load feature.parquet');
        setStatus('error');
      });
  }, [location, month]);

  const loadSummary = useCallback(
    async (row: FeatureRow) => {
      setSummaryStatus('loading');
      setError(null);
      try {
        const summary = await getBronzeBandSummary(row.band_index, {
          mission_type: row.mission_type,
          site: row.site,
          sensor: row.sensor,
          year: row.year,
          month: row.month
        });
        setSummary(summary);
        setSummaryStatus('ready');
      } catch (err: any) {
        setError(err?.message ?? 'Failed to load band summary');
        setSummaryStatus('error');
      }
    },
    [setSummary]
  );

  const chartPoints = useMemo(() => {
    if (!summary) return [];
    return summary.stats.map((p) => ({
      x: p.freq_hz / 1e6,
      y: p.power_mean
    }));
  }, [summary]);

  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">Gold feature view</p>
          <h1>Feature parquet (MinIO)</h1>
          <p className="muted">Query gold/survey/&lt;location&gt;/YYYY-MM/feature.parquet and drill into bronze band summaries via DuckDB/httpfs.</p>
        </div>
        <div className="controls">
          <label className="control">
            <span>Location</span>
            <input value={location} onChange={(e) => setLocation(e.target.value)} />
          </label>
          <label className="control">
            <span>Month (YYYY-MM)</span>
            <input value={month} onChange={(e) => setMonth(e.target.value)} />
          </label>
          <button onClick={loadFeature} className="button">
            {status === 'loading' ? 'Loading…' : 'Load feature'}
          </button>
        </div>
        {error && <p className="error">{error}</p>}
      </header>

      <section className="band-grid">
        {rows.map((row) => (
          <article key={`${row.location}-${row.month}-${row.band_index}`} className="band-card">
            <div className="band-card__heading">
              <h2>
                {row.band_label ?? `band${row.band_index}`} ({(row.start_hz / 1e6).toFixed(3)}-
                {(row.stop_hz / 1e6).toFixed(3)} MHz)
              </h2>
              <span className="badge">band {row.band_index}</span>
            </div>
            <dl className="band-card__meta">
              <MetaRow label="Traces" value={row.n_traces} />
              <MetaRow label="Freq bins" value={row.n_freqs} />
              <MetaRow label="Power (min/max/mean)" value={`${row.power_min.toFixed(1)} / ${row.power_max.toFixed(1)} / ${row.power_mean.toFixed(1)} dBm`} />
              <MetaRow label="Time span (unix)" value={`${row.unix_time_min} – ${row.unix_time_max}`} />
              <MetaRow label="Mission" value={row.mission_type} />
              <MetaRow label="Site / Sensor" value={`${row.site} / ${row.sensor}`} />
              <MetaRow label="Days" value={row.days.join(', ') || '—'} />
              <MetaRow label="Runs" value={row.run_ids.join(', ') || '—'} />
            </dl>
            <button className="button-link" onClick={() => loadSummary(row)}>
              {summaryStatus === 'loading' ? 'Loading…' : 'Load band summary'}
            </button>
          </article>
        ))}
        {rows.length === 0 && status === 'ready' && <p className="muted">No feature rows found for that location/month.</p>}
      </section>

      {summary && (
        <section className="band-card">
          <div className="band-card__heading">
            <h2>
              Band {summary.band_index} {summary.band_label ? `(${summary.band_label})` : ''} — mean power
            </h2>
            <span className="badge">summary</span>
          </div>
          <MetaRow label="Traces" value={summary.n_traces} />
          <MetaRow label="Freq range" value={`${(summary.start_hz / 1e6).toFixed(3)} - ${(summary.stop_hz / 1e6).toFixed(3)} MHz`} />
          <MetaRow label="Runs" value={summary.run_ids.join(', ') || '—'} />
          <MetaRow label="Days" value={summary.days.join(', ') || '—'} />
          <MiniLineChart points={chartPoints} />
        </section>
      )}
    </main>
  );
}

function MetaRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="meta-row">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function MiniLineChart({ points }: { points: { x: number; y: number }[] }) {
  if (!points.length) return <p className="muted">No points</p>;
  const width = 800;
  const height = 260;
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const scaleX = (x: number) => ((x - minX) / (maxX - minX || 1)) * width;
  const scaleY = (y: number) => height - ((y - minY) / (maxY - minY || 1)) * height;
  const path = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${scaleX(p.x)},${scaleY(p.y)}`).join(' ');
  return (
    <svg width={width} height={height} role="img" aria-label="Mean power vs frequency">
      <rect width={width} height={height} fill="#0b1021" rx="8" />
      <path d={path} stroke="#5ad" strokeWidth={2} fill="none" />
      <text x={8} y={20} fill="#9fb">Mean power (dBm)</text>
      <text x={width - 150} y={height - 8} fill="#9fb">
        Freq (MHz)
      </text>
    </svg>
  );
}

