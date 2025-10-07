import { useEffect, useState } from 'react';

import { PlaybackTick, createPlaybackSocket } from '../lib/api';

export interface PlaybackBarProps {
  bandId: string;
  windowSeconds?: number;
  fps?: number;
  onTick?: (tick: PlaybackTick) => void;
  className?: string;
}

export function PlaybackBar({ bandId, windowSeconds = 10, fps = 4, onTick, className }: PlaybackBarProps) {
  const [tick, setTick] = useState<PlaybackTick | null>(null);

  useEffect(() => {
    const socket = createPlaybackSocket(bandId, { window_s: windowSeconds, fps });
    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data) as PlaybackTick;
      setTick(payload);
      onTick?.(payload);
    };
    return () => {
      socket.close();
    };
  }, [bandId, windowSeconds, fps, onTick]);

  const classes = ['control-card', 'playback-card', className].filter(Boolean).join(' ');

  return (
    <div className={classes}>
      <div className="card-title">Playback Window</div>
      {tick ? (
        <div className="playback-details">
          <span className="metric">
            <span className="metric-label">Window</span>
            <span className="metric-value">
              {tick.t0.toFixed(2)}s → {tick.t1.toFixed(2)}s
            </span>
          </span>
          <span className="metric">
            <span className="metric-label">Cursor UNIX</span>
            <span className="metric-value">{tick.cursor_unix.toFixed(2)}</span>
          </span>
        </div>
      ) : (
        <p className="muted">Waiting for live playback updates…</p>
      )}
    </div>
  );
}

export default PlaybackBar;
