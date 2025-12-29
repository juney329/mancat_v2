import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  FeatureRow,
  BronzeBandSummary,
  FeatureLocations,
  FeatureMonths,
  getFeature,
  getBronzeBandSummary,
  getFeatureLocations,
  getFeatureMonths
} from '../lib/api';

type Status = 'idle' | 'loading' | 'error' | 'ready';

export default function FeaturePage() {
  const [locations, setLocations] = useState<string[]>([]);
  const [location, setLocation] = useState<string>('');
  const [months, setMonths] = useState<string[]>([]);
  const [month, setMonth] = useState<string>('');
  const [rows, setRows] = useState<FeatureRow[]>([]);
  const [status, setStatus] = useState<Status>('idle');
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<BronzeBandSummary | null>(null);
  const [summaryStatus, setSummaryStatus] = useState<Status>('idle');

  // Load locations on mount
  useEffect(() => {
    getFeatureLocations()
      .then((data) => {
        setLocations(data.locations);
        if (data.locations.length > 0 && !location) {
          setLocation(data.locations[0]);
        }
      })
      .catch((err) => {
        console.error('Failed to load locations', err);
      });
  }, []);

  // Load months when location changes
  useEffect(() => {
    if (!location) {
      setMonths([]);
      setMonth('');
      return;
    }
    getFeatureMonths(location)
      .then((data) => {
        setMonths(data.months);
        if (data.months.length > 0 && !month) {
          setMonth(data.months[0]);
        } else if (!data.months.includes(month)) {
          setMonth('');
        }
      })
      .catch((err) => {
        console.error('Failed to load months', err);
        setMonths([]);
      });
  }, [location]);

  const loadFeature = useCallback(() => {
    if (!location || !month) {
      setError('Please select location and month');
      return;
    }
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
          month: row.month,
          use_feature: true  // Use feature.parquet by default to avoid slow bronze scan
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

  const formatDateTime = (unixTime: number | null): string => {
    if (unixTime === null || unixTime === undefined) return '—';
    return new Date(unixTime * 1000).toLocaleString();
  };

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
            <select value={location} onChange={(e) => setLocation(e.target.value)}>
              <option value="">Select location</option>
              {locations.map((loc) => (
                <option key={loc} value={loc}>
                  {loc}
                </option>
              ))}
            </select>
          </label>
          <label className="control">
            <span>Month</span>
            <select value={month} onChange={(e) => setMonth(e.target.value)} disabled={!location}>
              <option value="">Select month</option>
              {months.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
          <button onClick={loadFeature} className="button" disabled={!location || !month || status === 'loading'}>
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
              <MetaRow label="Time span" value={`${formatDateTime(row.unix_time_min)} – ${formatDateTime(row.unix_time_max)}`} />
              <MetaRow label="Mission" value={row.mission_type} />
              <MetaRow label="Site / Sensor" value={`${row.site} / ${row.sensor}`} />
              <MetaRow label="Days" value={row.days.join(', ') || '—'} />
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
              Band {summary.band_index} {summary.band_label ? `(${summary.band_label})` : ''} — summary
              {summary.source && (
                <span style={{ fontSize: '0.8em', marginLeft: '0.5em', opacity: 0.7 }}>
                  (from {summary.source})
                </span>
              )}
            </h2>
            <span className="badge">summary</span>
          </div>
          <MetaRow label="Traces" value={summary.n_traces} />
          <MetaRow label="Freq range" value={`${(summary.start_hz / 1e6).toFixed(3)} - ${(summary.stop_hz / 1e6).toFixed(3)} MHz`} />
          <MetaRow label="Days" value={summary.days.join(', ') || '—'} />
          {summary.stats && summary.stats.length > 0 ? (
            <MiniLineChart points={chartPoints} />
          ) : (
            <p className="muted">Per-frequency stats not available (using feature.parquet aggregate stats only)</p>
          )}
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

