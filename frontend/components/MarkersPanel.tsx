import { FormEvent, useMemo, useState } from 'react';

import type { Marker } from '../lib/api';

export interface MarkersPanelProps {
  markers: Marker[];
  onCreate: (marker: Marker) => void;
  onDelete: (id: string) => void;
}

export function MarkersPanel({ markers, onCreate, onDelete }: MarkersPanelProps) {
  const [form, setForm] = useState<Marker>({ id: '', freq: 0, label: '', color: '#ff0000', width: 0 });

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!form.id) {
      alert('Marker ID is required.');
      return;
    }
    onCreate(form);
    setForm({ id: '', freq: 0, label: '', color: '#ff0000', width: 0 });
  };

  const markerList = useMemo(
    () =>
      markers.map((marker) => (
        <li key={marker.id} style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem' }}>
          <span>
            <strong>{marker.id}</strong> @ {marker.freq.toFixed(2)} Hz
            {marker.width ? ` ± ${marker.width / 2} Hz` : ''}
          </span>
          <button type="button" onClick={() => onDelete(marker.id)}>
            Remove
          </button>
        </li>
      )),
    [markers, onDelete]
  );

  return (
    <div style={{ background: '#11141f', padding: '1rem', borderRadius: '0.75rem', border: '1px solid rgba(255,255,255,0.08)' }}>
      <h3 style={{ marginTop: 0 }}>Markers</h3>
      <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 1rem 0', display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
        {markerList}
      </ul>
      <form onSubmit={handleSubmit} style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '0.75rem' }}>
        <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.85rem' }}>
          ID
          <input value={form.id} onChange={(event) => setForm({ ...form, id: event.target.value })} />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.85rem' }}>
          Label
          <input value={form.label ?? ''} onChange={(event) => setForm({ ...form, label: event.target.value })} />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.85rem' }}>
          Frequency (Hz)
          <input
            type="number"
            value={form.freq}
            onChange={(event) => setForm({ ...form, freq: Number(event.target.value) })}
            step="0.1"
          />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.85rem' }}>
          Width (Hz)
          <input
            type="number"
            value={form.width ?? 0}
            onChange={(event) => setForm({ ...form, width: Number(event.target.value) })}
            step="0.1"
          />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.85rem' }}>
          Color
          <input type="color" value={form.color ?? '#ff0000'} onChange={(event) => setForm({ ...form, color: event.target.value })} />
        </label>
        <button type="submit" style={{ alignSelf: 'end' }}>
          Add Marker
        </button>
      </form>
    </div>
  );
}

export default MarkersPanel;
