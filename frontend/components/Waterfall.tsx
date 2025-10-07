import { useEffect, useMemo, useRef, useState } from 'react';

import { getWaterfallTile } from '../lib/api';

export interface WaterfallProps {
  bandId: string;
  f0?: number;
  f1?: number;
  t0?: number;
  t1?: number;
  maxw?: number;
  maxt?: number;
  onBoundsChange?: (bounds: { f0: number; f1: number; t0: number; t1: number }) => void;
}

interface TileState {
  url: string;
  freqStart: number;
  freqEnd: number;
  timeStart: number;
  timeEnd: number;
}

export function Waterfall({ bandId, f0, f1, t0, t1, maxw = 1600, maxt = 600, onBoundsChange }: WaterfallProps) {
  const [tile, setTile] = useState<TileState | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [containerWidth, setContainerWidth] = useState<number>(0);
  const [naturalSize, setNaturalSize] = useState<{ w: number; h: number } | null>(null);

  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;

    setLoading(true);
    setError(null);

    (async () => {
      try {
        const { blob, headers } = await getWaterfallTile(bandId, {
          f0,
          f1,
          t0,
          t1,
          maxw,
          maxt,
          fmt: 'png'
        });
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        // Backend returns Hz; align with summary (also Hz)
        const freqStart = Number(headers.get('X-Freq-Start') ?? f0 ?? 0);
        const freqEnd = Number(headers.get('X-Freq-End') ?? f1 ?? freqStart + 1);
        const timeStart = Number(headers.get('X-Time-Start') ?? t0 ?? 0);
        const timeEnd = Number(headers.get('X-Time-End') ?? t1 ?? timeStart + 1);
        setTile((current) => {
          if (current) {
            URL.revokeObjectURL(current.url);
          }
          return {
            url: objectUrl as string,
            freqStart,
            freqEnd,
            timeStart,
            timeEnd
          };
        });
        try { onBoundsChange?.({ f0: freqStart, f1: freqEnd, t0: timeStart, t1: timeEnd }); } catch {}
        setLoading(false);
      } catch (err) {
        if (cancelled) return;
        console.error('Failed to load waterfall', err);
        setTile((current) => {
          if (current) {
            URL.revokeObjectURL(current.url);
          }
          return null;
        });
        setError('Unable to load waterfall image.');
        setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [bandId, f0, f1, t0, t1, maxw, maxt]);

  // Track container width to compute integer scaling height and avoid subpixel gaps
  useEffect(() => {
    if (!containerRef.current) return;
    const el = containerRef.current;
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) {
        setContainerWidth(Math.max(0, Math.floor(e.contentRect.width)));
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const scaledHeightPx = useMemo(() => {
    if (!naturalSize || containerWidth <= 0) return undefined;
    const scale = containerWidth / Math.max(1, naturalSize.w);
    const h = Math.max(1, Math.round(naturalSize.h * scale));
    return h;
  }, [naturalSize, containerWidth]);

  const axisText = useMemo(() => {
    if (!tile) return null;
    const freq = `${tile.freqStart.toFixed(2)} MHz → ${tile.freqEnd.toFixed(2)} MHz`;
    const time = `${tile.timeStart.toFixed(2)} s → ${tile.timeEnd.toFixed(2)} s`;
    return { freq, time };
  }, [tile]);

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '0.75rem',
        background: '#0f1320',
        borderRadius: '0.75rem',
        padding: '1rem',
        border: '1px solid rgba(255,255,255,0.08)'
      }}
    >
      <div ref={containerRef} style={{ position: 'relative', minHeight: 280, paddingLeft: 56, paddingRight: 24 }}>
        {tile && !loading && !error ? (
          <img
            src={tile.url}
            alt="Waterfall heatmap"
            style={{
              display: 'block',
              width: '100%',
              height: scaledHeightPx ? `${scaledHeightPx}px` : 'auto',
              imageRendering: 'pixelated',
              WebkitTransform: 'translateZ(0)',
              backfaceVisibility: 'hidden',
              borderRadius: '0.5rem'
            }}
            onLoad={(e) => setNaturalSize({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
            draggable={false}
          />
        ) : (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '100%',
              height: 280,
              borderRadius: '0.5rem',
              background: 'rgba(26,30,43,0.6)',
              border: '1px dashed rgba(255,255,255,0.1)',
              color: 'rgba(255,255,255,0.6)'
            }}
          >
            {loading ? 'Loading waterfall…' : error ?? 'No waterfall available.'}
          </div>
        )}
        {tile ? (
          <div
            style={{
              position: 'absolute',
              right: 16,
              top: 16,
              width: 12,
              height: 160,
              background:
                'linear-gradient(180deg, rgb(255,0,0) 0%, rgb(255,165,0) 20%, rgb(255,255,0) 40%, rgb(0,255,0) 60%, rgb(0,0,255) 80%, rgb(0,0,0) 100%)',
              borderRadius: 6,
              border: '1px solid rgba(255,255,255,0.3)'
            }}
          />
        ) : null}
      </div>
      {axisText ? (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', fontSize: '0.85rem', opacity: 0.85 }}>
          <span><strong>Frequency:</strong> {axisText.freq}</span>
          <span><strong>Time:</strong> {axisText.time}</span>
        </div>
      ) : null}
    </div>
  );
}

export default Waterfall;
