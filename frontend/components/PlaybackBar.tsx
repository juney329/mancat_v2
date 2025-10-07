import { useCallback, useEffect, useMemo, useState } from 'react';

import { PlaybackTick, createPlaybackSocket } from '../lib/api';

export interface PlaybackBarProps {
  bandId: string;
  windowSeconds?: number;
  fps?: number;
  onTick?: (tick: PlaybackTick) => void;
}

type ConnectionState = 'idle' | 'connecting' | 'streaming' | 'error';

export function PlaybackBar({ bandId, windowSeconds = 10, fps = 4, onTick }: PlaybackBarProps) {
  const [tick, setTick] = useState<PlaybackTick | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [connectionState, setConnectionState] = useState<ConnectionState>('idle');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!isPlaying) {
      return undefined;
    }

    setErrorMessage(null);
    setConnectionState('connecting');

    const socket = createPlaybackSocket(bandId, { window_s: windowSeconds, fps });
    let isActive = true;

    socket.onopen = () => {
      if (!isActive) return;
      setConnectionState('streaming');
    };

    socket.onmessage = (event) => {
      if (!isActive) return;
      const payload = JSON.parse(event.data) as PlaybackTick;
      setTick(payload);
      setConnectionState('streaming');
      onTick?.(payload);
    };

    socket.onerror = () => {
      if (!isActive) return;
      setConnectionState('error');
      setErrorMessage('Playback connection failed.');
    };

    socket.onclose = () => {
      if (!isActive) return;
      setConnectionState('error');
      setErrorMessage('Playback disconnected unexpectedly.');
    };

    return () => {
      isActive = false;
      socket.close();
      setConnectionState('idle');
    };
  }, [bandId, windowSeconds, fps, isPlaying, onTick]);

  const togglePlayback = useCallback(() => {
    setIsPlaying((value) => !value);
    setErrorMessage(null);
  }, []);

  const statusText = useMemo(() => {
    if (connectionState === 'error') {
      return errorMessage ?? 'Playback error.';
    }
    if (!isPlaying) {
      if (tick) {
        return `Paused at ${tick.t0.toFixed(2)}s → ${tick.t1.toFixed(2)}s.`;
      }
      return 'Playback paused. Press play to stream new data.';
    }
    if (connectionState === 'connecting') {
      return 'Connecting…';
    }
    if (!tick) {
      return 'Waiting for playback data…';
    }
    return `Window: ${tick.t0.toFixed(2)}s → ${tick.t1.toFixed(2)}s | Cursor UNIX: ${tick.cursor_unix.toFixed(2)}`;
  }, [connectionState, errorMessage, isPlaying, tick]);

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
      <button
        type="button"
        onClick={togglePlayback}
        style={{
          appearance: 'none',
          border: '1px solid rgba(255,255,255,0.2)',
          background: isPlaying ? '#ff8c42' : '#2a3144',
          color: '#fff',
          padding: '0.35rem 0.85rem',
          borderRadius: '999px',
          cursor: 'pointer',
          fontWeight: 600,
          textTransform: 'uppercase',
          letterSpacing: '0.05em'
        }}
        aria-pressed={isPlaying}
      >
        {isPlaying ? 'Pause' : 'Play'}
      </button>
      <span style={{ fontSize: '0.85rem', opacity: 0.9 }}>{statusText}</span>
    </div>
  );
}

export default PlaybackBar;
