import { FormEvent, useMemo, useState } from 'react';

import type { Marker } from '../lib/api';

export interface MarkersPanelProps {
  markers: Marker[];
  onCreate: (marker: Marker) => void;
  onDelete: (id: string) => void;
  className?: string;
}

export function MarkersPanel({ markers, onCreate, onDelete, className }: MarkersPanelProps) {
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
        <li key={marker.id} className="marker-item">
          <div className="marker-summary">
            <span className="marker-color" style={{ background: marker.color ?? '#ff0000' }} aria-hidden />
            <div>
              <div className="marker-id">{marker.id}</div>
              <div className="marker-meta">
                {marker.freq.toFixed(2)} Hz{marker.width ? ` · span ±${(marker.width / 2).toFixed(2)} Hz` : ''}
              </div>
            </div>
          </div>
          <button type="button" className="ghost" onClick={() => onDelete(marker.id)}>
            Remove
          </button>
        </li>
      )),
    [markers, onDelete]
  );

  const classes = ['control-card', 'markers-panel', className].filter(Boolean).join(' ');

  return (
    <div className={classes}>
      <div className="card-title">Markers</div>
      {markers.length === 0 ? (
        <p className="muted">No markers defined yet. Use the form below to annotate the trace.</p>
      ) : (
        <ul className="marker-list">{markerList}</ul>
      )}
      <form onSubmit={handleSubmit} className="field-grid">
        <label className="field-group">
          <span className="field-label">ID</span>
          <input value={form.id} onChange={(event) => setForm({ ...form, id: event.target.value })} />
        </label>
        <label className="field-group">
          <span className="field-label">Label</span>
          <input value={form.label ?? ''} onChange={(event) => setForm({ ...form, label: event.target.value })} />
        </label>
        <label className="field-group">
          <span className="field-label">Frequency (Hz)</span>
          <input
            type="number"
            value={form.freq}
            onChange={(event) => setForm({ ...form, freq: Number(event.target.value) })}
            step="0.1"
          />
        </label>
        <label className="field-group">
          <span className="field-label">Width (Hz)</span>
          <input
            type="number"
            value={form.width ?? 0}
            onChange={(event) => setForm({ ...form, width: Number(event.target.value) })}
            step="0.1"
          />
        </label>
        <label className="field-group">
          <span className="field-label">Color</span>
          <input type="color" value={form.color ?? '#ff0000'} onChange={(event) => setForm({ ...form, color: event.target.value })} />
        </label>
        <div className="actions">
          <button type="submit" className="primary">
            Add Marker
          </button>
        </div>
      </form>
    </div>
  );
}

export default MarkersPanel;
