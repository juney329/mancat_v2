import { useCallback, useEffect, useState } from 'react';

import {
  listBronzeSites,
  listBronzeMonths,
  listBandsBySiteMonth,
  type BronzeBandInfo,
  uploadAssignments,
} from '../lib/api';

type Status = 'idle' | 'loading' | 'error' | 'ready';

export default function FeaturePage() {
  const [sites, setSites] = useState<string[]>([]);
  const [site, setSite] = useState<string>('');
  const [months, setMonths] = useState<string[]>([]);
  const [month, setMonth] = useState<string>('');
  const [year, setYear] = useState<string>('');
  const [bands, setBands] = useState<BronzeBandInfo[]>([]);
  const [status, setStatus] = useState<Status>('idle');
  const [error, setError] = useState<string | null>(null);
  const [uploadStatus, setUploadStatus] = useState<Status>('idle');
  const [uploadError, setUploadError] = useState<string | null>(null);

  // Load sites on mount
  useEffect(() => {
    listBronzeSites()
      .then((data) => {
        setSites(data.sites);
        if (data.sites.length > 0 && !site) {
          setSite(data.sites[0]);
        }
      })
      .catch((err) => {
        console.error('Failed to load sites', err);
        setError('Failed to load sites from bronze');
      });
  }, []);

  // Load months when site changes
  useEffect(() => {
    if (!site) {
      setMonths([]);
      setMonth('');
      setYear('');
      setBands([]);
      return;
    }
    // Reset month and clear bands when site changes
    setMonth('');
    setYear('');
    setBands([]);
    listBronzeMonths(site)
      .then((data) => {
        setMonths(data.months);
        if (data.months.length > 0) {
          const firstMonth = data.months[0];
          setMonth(firstMonth);
        }
      })
      .catch((err) => {
        console.error('Failed to load months', err);
        setError('Failed to load months for site');
        setMonths([]);
        setMonth('');
      });
  }, [site]);

  // Parse year and month from YYYY-MM format
  useEffect(() => {
    if (month && month.includes('-')) {
      const [y, m] = month.split('-');
      setYear(y);
      // month state already contains YYYY-MM, but we also need just MM for API calls
    }
  }, [month]);

  const loadBands = useCallback(() => {
    if (!site || !month) {
      setError('Please select site and month');
      return;
    }
    
    // Extract year and month from YYYY-MM format
    const [y, m] = month.split('-');
    if (!y || !m) {
      setError('Invalid month format');
      return;
    }

    setStatus('loading');
    setError(null);
    listBandsBySiteMonth(site, y, m)
      .then((data) => {
        setBands(data.bands);
        setStatus('ready');
      })
      .catch((err) => {
        setError(err?.message ?? 'Failed to load bands');
        setStatus('error');
      });
  }, [site, month]);

  const handleFileUpload = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (!file || !site || !month) {
        setUploadError('Please select site and month before uploading');
        return;
      }

      setUploadStatus('loading');
      setUploadError(null);
      try {
        // Use site as location for assignments (legacy compatibility)
        const result = await uploadAssignments(site, month, file);
        setUploadStatus('ready');
        alert(`Upload successful! ${result.rows} assignments uploaded.`);
        event.target.value = ''; // Reset file input
      } catch (err: any) {
        setUploadError(err?.message ?? 'Upload failed');
        setUploadStatus('error');
      }
    },
    [site, month]
  );

  const handleBandClick = (band: BronzeBandInfo) => {
    const [y, m] = month.split('-');
    const url = `/feature-bands/${site}/${y}/${m}/${band.band_index}?mission_type=${encodeURIComponent(band.mission_type)}&sensor=${encodeURIComponent(band.sensor)}`;
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">Bronze band discovery</p>
          <h1>Band Explorer (MinIO Bronze)</h1>
          <p className="muted">Browse bands from bronze data by site and month. Click a band to view detailed analysis with assignments overlay.</p>
        </div>
        <div className="controls">
          <label className="control">
            <span>Site</span>
            <select value={site} onChange={(e) => setSite(e.target.value)}>
              <option value="">Select site</option>
              {sites.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <label className="control">
            <span>Month (YYYY-MM)</span>
            <select value={month} onChange={(e) => setMonth(e.target.value)} disabled={!site}>
              <option value="">Select month</option>
              {months.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
          <button onClick={loadBands} className="button" disabled={!site || !month || status === 'loading'}>
            {status === 'loading' ? 'Loading Bands…' : 'Load Bands'}
          </button>
          <label className="control">
            <span>Upload Assignments CSV</span>
            <input
              type="file"
              accept=".csv"
              onChange={handleFileUpload}
              disabled={!site || !month || uploadStatus === 'loading'}
              style={{ fontSize: '0.9em' }}
            />
          </label>
        </div>
        {error && <p className="error">{error}</p>}
        {uploadError && <p className="error">Upload error: {uploadError}</p>}
        {uploadStatus === 'loading' && <p className="muted">Uploading assignments CSV...</p>}
      </header>

      <section className="band-grid">
        {bands.map((band) => (
          <article key={`${band.band_index}-${band.mission_type}-${band.sensor}`} className="band-card">
            <div className="band-card__heading">
              <h2>
                {band.band_label ?? `band${band.band_index}`}
              </h2>
              <span className="badge">band {band.band_index}</span>
            </div>
            <dl className="band-card__meta">
              <MetaRow label="Mission Type" value={band.mission_type} />
              <MetaRow label="Site / Sensor" value={`${site} / ${band.sensor}`} />
              <MetaRow label="Month" value={month} />
              <MetaRow label="Days" value={band.days.join(', ') || '—'} />
              <MetaRow label="Run IDs" value={band.run_ids.join(', ') || '—'} />
            </dl>
            <button
              onClick={() => handleBandClick(band)}
              className="button-link"
            >
              Open Band Detail (New Tab)
            </button>
          </article>
        ))}
        {bands.length === 0 && status === 'ready' && <p className="muted">No bands found for that site/month.</p>}
        {bands.length === 0 && status === 'idle' && <p className="muted">Select a site and month, then click "Load Bands" to view available bands.</p>}
      </section>
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
