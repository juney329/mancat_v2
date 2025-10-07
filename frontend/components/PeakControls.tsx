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
        <label className="field-group">
          <span className="field-label">Curve</span>
          <select value={curve} onChange={(event) => setCurve(event.target.value)}>
            {curves.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <label className="field-group">
          <span className="field-label">Min Height</span>
          <input
            type="number"
            value={height ?? ''}
            onChange={(event) => setHeight(event.target.value ? Number(event.target.value) : undefined)}
          />
        </label>
        <label className="field-group">
          <span className="field-label">Prominence</span>
          <input
            type="number"
            value={prominence ?? ''}
            onChange={(event) =>
              setProminence(event.target.value ? Number(event.target.value) : undefined)
            }
          />
        </label>
        <label className="field-group">
          <span className="field-label">Distance</span>
          <input
            type="number"
            value={distance ?? ''}
            onChange={(event) => setDistance(event.target.value ? Number(event.target.value) : undefined)}
          />
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
