import { FormEvent, useEffect, useState } from 'react';

import { PeakItem, PeakRequest, postPeaks } from '../lib/api';

export interface PeakControlsProps {
  bandId: string;
  curves: string[];
  freqWindow?: { f0?: number; f1?: number };
  onPeaks: (peaks: PeakItem[]) => void;
  className?: string;
}

export function PeakControls({ bandId, curves, freqWindow, onPeaks, className }: PeakControlsProps) {
  const [curve, setCurve] = useState(curves[0] ?? 'Avg');
  const [height, setHeight] = useState<number | undefined>();
  const [prominence, setProminence] = useState<number | undefined>(10);
  const [distance, setDistance] = useState<number | undefined>(5);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (curves.length === 0) {
      setCurve('Avg');
    } else if (!curves.includes(curve)) {
      setCurve(curves[0]);
    }
  }, [curves, curve]);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setLoading(true);
    try {
      const payload: PeakRequest = { curve, height, prominence, distance, ...freqWindow };
      const peaks = await postPeaks(bandId, payload);
      onPeaks(peaks);
    } finally {
      setLoading(false);
    }
  };

  const classes = ['control-card', 'peak-controls', className].filter(Boolean).join(' ');

  return (
    <form onSubmit={handleSubmit} className={classes}>
      <div className="card-title">Peak Detection</div>
      <div className="field-grid">
        <label className="field-group" title="Which curve to use for peak detection (e.g., Avg, Max).">
          <span className="field-label">Curve to analyze</span>
          <select value={curve} onChange={(event) => setCurve(event.target.value)}>
            {curves.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
          <small className="muted">Select the trace used for detection.</small>
        </label>
        <label className="field-group" title="Minimum amplitude threshold in dB. Peaks below this value are ignored.">
          <span className="field-label">Minimum height (dB)</span>
          <input
            type="number"
            step="0.1"
            value={height ?? ''}
            placeholder="e.g., -90"
            onChange={(event) => setHeight(event.target.value ? Number(event.target.value) : undefined)}
          />
          <small className="muted">Ignore peaks below this level.</small>
        </label>
        <label className="field-group" title="Required vertical distance from a peak to its surroundings, in dB.">
          <span className="field-label">Prominence (dB)</span>
          <input
            type="number"
            step="0.1"
            value={prominence ?? ''}
            onChange={(event) =>
              setProminence(event.target.value ? Number(event.target.value) : undefined)
            }
          />
          <small className="muted">Higher = fewer, more distinct peaks.</small>
        </label>
        <label className="field-group" title="Minimum separation between peaks, measured in frequency bins (data points).">
          <span className="field-label">Min distance (bins)</span>
          <input
            type="number"
            step="1"
            min="1"
            value={distance ?? ''}
            onChange={(event) => setDistance(event.target.value ? Number(event.target.value) : undefined)}
          />
          <small className="muted">Increase to avoid detecting very close peaks as separate.</small>
        </label>
      </div>
      <div className="actions">
        <button type="submit" className="primary" disabled={loading}>
          {loading ? 'Detecting…' : 'Detect Peaks'}
        </button>
      </div>
    </form>
  );
}

export default PeakControls;
