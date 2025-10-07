import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/router';

import TracePlot from '../../components/TracePlot';
import Waterfall from '../../components/Waterfall';
import PeakControls from '../../components/PeakControls';
import MarkersPanel from '../../components/MarkersPanel';
import BandsSidebar from '../../components/BandsSidebar';
import type { Marker, PeakItem, SummaryResponse } from '../../lib/api';
import { getMarkers, getSummary, saveMarkers } from '../../lib/api';

export default function BandDetailPage() {
  const router = useRouter();
  const { id } = router.query as { id?: string };
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [peaks, setPeaks] = useState<PeakItem[]>([]);
  const [markers, setMarkers] = useState<Marker[]>([]);
  const [freqWindow, setFreqWindow] = useState<{ f0?: number; f1?: number }>({});
  const [wfBounds, setWfBounds] = useState<{ f0: number; f1: number; t0: number; t1: number } | null>(null);

  useEffect(() => {
    if (!id) return;
    getSummary(id, { max_pts: 1200 })
      .then((data) => {
        setSummary(data);
        const start = data.freqs.length > 0 ? data.freqs[0] : undefined;
        const end = data.freqs.length > 0 ? data.freqs[data.freqs.length - 1] : start;
        setFreqWindow({ f0: start, f1: end });
      })
      .catch((error) => console.error('Failed to load summary', error));
    getMarkers(id)
      .then(setMarkers)
      .catch((error) => console.error('Failed to load markers', error));
  }, [id]);

  const curves = useMemo<Record<string, number[]>>(() => {
    if (!summary) return {};
    const { freqs, ...rest } = summary;
    return rest as Record<string, number[]>;
  }, [summary]);

  const handleZoom = useCallback(
    (range: { f0: number; f1: number }) => {
      if (!id) return;
      setFreqWindow(range);
      getSummary(id, { f0: range.f0, f1: range.f1, max_pts: 1200 })
        .then((data) => setSummary(data))
        .catch((error) => console.error('Failed to update summary', error));
    },
    [id]
  );

  const handleCreateMarker = useCallback(
    (marker: Marker) => {
      if (!id) return;
      const updated = [...markers.filter((m) => m.id !== marker.id), marker];
      saveMarkers(id, updated)
        .then(setMarkers)
        .catch((error) => console.error('Failed to save markers', error));
    },
    [id, markers]
  );

  const handleDeleteMarker = useCallback(
    (markerId: string) => {
      if (!id) return;
      const updated = markers.filter((marker) => marker.id !== markerId);
      saveMarkers(id, updated)
        .then(setMarkers)
        .catch((error) => console.error('Failed to save markers', error));
    },
    [id, markers]
  );

  if (!id) {
    return <main>Loading…</main>;
  }

  if (!summary) {
    return <main className="band-shell">Loading summary…</main>;
  }

  const freqs = summary.freqs ?? [];
  const freqStart = freqs[0] ?? 0;
  const freqEnd = freqs[freqs.length - 1] ?? freqStart;
  const windowStart = freqWindow.f0 ?? freqStart;
  const windowEnd = freqWindow.f1 ?? freqEnd;
  const overviewMetrics = [
    { label: 'Frequency Start', value: formatFrequency(freqStart) },
    { label: 'Frequency End', value: formatFrequency(freqEnd) },
    { label: 'Span', value: formatSpan(Math.max(0, freqEnd - freqStart)) },
    { label: 'Zoom Window', value: `${formatFrequency(windowStart)} → ${formatFrequency(windowEnd)}` }
  ];

  return (
    <div style={{ display: 'flex' }}>
      <BandsSidebar />
      <main className="band-shell" style={{ flex: 1 }}>
      <header className="band-header">
        <div>
          <p className="eyebrow">RF Spectrum Explorer</p>
          <h1>Band {id}</h1>
          <p className="muted">Composite traces and a static waterfall snapshot for the selected RF band.</p>
        </div>
        <div className="header-status">
          <span className="badge">Static View</span>
          <span className="muted">Latest available capture</span>
        </div>
      </header>
      <div className="band-layout">
        <aside className="band-sidebar">
          <section className="control-card overview-card">
            <div className="card-title">Band Overview</div>
            <dl className="overview-metrics">
              {overviewMetrics.map((metric) => (
                <div key={metric.label} className="meta-row">
                  <dt>{metric.label}</dt>
                  <dd>{metric.value}</dd>
                </div>
              ))}
            </dl>
          </section>
          <PeakControls
            bandId={id}
            curves={Object.keys(curves)}
            freqWindow={freqWindow}
            onPeaks={setPeaks}
            className="sidebar-card"
          />
          <MarkersPanel
            markers={markers}
            onCreate={handleCreateMarker}
            onDelete={handleDeleteMarker}
            className="sidebar-card"
          />
        </aside>
        <div className="panel-stack">
          <section className="panel-card panel-card--trace" id="summary">
            <div className="panel-header">
              <div>
                <h2>Spectrum Composite</h2>
                <p className="muted">Average power traces across the current frequency selection.</p>
              </div>
              <div className="header-metric">
                <span className="metric-label">Zoom Span</span>
                <span className="metric-value">{formatSpan(Math.max(0, windowEnd - windowStart))}</span>
              </div>
            </div>
            <div className="panel-body panel-body--tall">
              <TracePlot
                freqs={summary.freqs}
                curves={curves}
                peaks={peaks}
                markers={markers}
                onZoom={handleZoom}
                xRange={wfBounds ? { f0: wfBounds.f0, f1: wfBounds.f1 } : undefined}
              />
            </div>
          </section>
          <section className="panel-card panel-card--waterfall" id="waterfall">
            <div className="panel-header">
              <div>
                <h2>Waterfall Snapshot</h2>
                <p className="muted">Latest available energy density aligned to the selected frequency window.</p>
              </div>
              <div className="header-metric">
                <span className="metric-label">Frequency Window</span>
                <span className="metric-value">{formatFrequency(windowStart)} → {formatFrequency(windowEnd)}</span>
              </div>
            </div>
            <div className="panel-body panel-body--tall">
              <Waterfall bandId={id} f0={freqWindow.f0} f1={freqWindow.f1} onBoundsChange={setWfBounds} />
            </div>
          </section>
          <section className="panel-card panel-card--peaks" id="peaks">
            <div className="panel-header">
              <div>
                <h2>Detected Peaks</h2>
                <p className="muted">Results from the latest peak detection run.</p>
              </div>
              <span className="badge badge--outline">{peaks.length} peaks</span>
            </div>
            <div className="panel-body panel-body--list">
              {peaks.length === 0 ? (
                <p className="muted">Run a peak detection above to populate this table.</p>
              ) : (
                <table className="peaks-table">
                  <thead>
                    <tr>
                      <th>Frequency</th>
                      <th>Power</th>
                      <th>Prominence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {peaks.map((peak) => (
                      <tr key={`${peak.freq}-${peak.value}`}>
                        <td>{formatFrequency(peak.freq)}</td>
                        <td>{peak.value.toFixed(2)} dB</td>
                        <td>{formatProminence(peak.properties)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </section>
        </div>
      </div>
      </main>
    </div>
  );
}

function formatFrequency(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(2)} GHz`;
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(2)} MHz`;
  if (abs >= 1_000) return `${(value / 1_000).toFixed(2)} kHz`;
  return `${value.toFixed(2)} Hz`;
}

function formatSpan(span: number): string {
  return formatFrequency(span);
}

function formatProminence(properties: Record<string, number>): string {
  const prominence = properties.prominences ?? properties.prominence;
  return prominence !== undefined ? `${prominence.toFixed(2)} dB` : '—';
}
