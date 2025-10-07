import { useEffect, useState } from 'react';

import { PlaybackTick, createPlaybackSocket } from '../lib/api';

export interface PlaybackBarProps {
  bandId: string;
  windowSeconds?: number;
  fps?: number;
  onTick?: (tick: PlaybackTick) => void;
}

export function PlaybackBar({ bandId, windowSeconds = 10, fps = 4, onTick }: PlaybackBarProps) {
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

  return (
    <div
      style={{
        display: 'flex',
        gap: '1rem',
        alignItems: 'center',
        background: '#1a1e2b',
        padding: '0.75rem 1rem',
        borderRadius: '0.75rem',
        border: '1px solid rgba(255,255,255,0.1)'
      }}
    >
      <strong>Playback</strong>
      {tick ? (
        <span>
          Window: {tick.t0.toFixed(2)}s → {tick.t1.toFixed(2)}s &nbsp;|&nbsp; Cursor UNIX: {tick.cursor_unix.toFixed(2)}
        </span>
      ) : (
        <span>Waiting for server…</span>
      )}
    </div>
  );
}

export default PlaybackBar;
