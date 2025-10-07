import { FormEvent, useEffect, useState } from 'react';

import { PeakItem, PeakRequest, postPeaks } from '../lib/api';

export interface PeakControlsProps {
  bandId: string;
  curves: string[];
  freqWindow?: { f0?: number; f1?: number };
  onPeaks: (peaks: PeakItem[]) => void;
}

export function PeakControls({ bandId, curves, freqWindow, onPeaks }: PeakControlsProps) {
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

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-end' }}>
      <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.85rem' }}>
        Curve
        <select value={curve} onChange={(event) => setCurve(event.target.value)}>
          {curves.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>
      <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.85rem' }}>
        Min Height
        <input
          type="number"
          value={height ?? ''}
          onChange={(event) => setHeight(event.target.value ? Number(event.target.value) : undefined)}
        />
      </label>
      <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.85rem' }}>
        Prominence
        <input
          type="number"
          value={prominence ?? ''}
          onChange={(event) =>
            setProminence(event.target.value ? Number(event.target.value) : undefined)
          }
        />
      </label>
      <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.85rem' }}>
        Distance
        <input
          type="number"
          value={distance ?? ''}
          onChange={(event) => setDistance(event.target.value ? Number(event.target.value) : undefined)}
        />
      </label>
      <button type="submit" disabled={loading}>
        {loading ? 'Detecting…' : 'Detect Peaks'}
      </button>
    </form>
  );
}

export default PeakControls;
