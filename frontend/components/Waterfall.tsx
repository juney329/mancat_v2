import { useEffect, useMemo, useRef, useState } from 'react';
import DeckGL from '@deck.gl/react';
import { BitmapLayer } from '@deck.gl/layers';
import { OrthographicView } from '@deck.gl/core';

import { getWaterfallTile } from '../lib/api';

export interface WaterfallProps {
  bandId: string;
  f0?: number;
  f1?: number;
  t0?: number;
  t1?: number;
  maxw?: number;
  maxt?: number;
}

interface TileState {
  url: string;
  bounds: [number, number, number, number];
}

export function Waterfall({ bandId, f0, f1, t0, t1, maxw = 1600, maxt = 600 }: WaterfallProps) {
  const [tile, setTile] = useState<TileState | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [containerSize, setContainerSize] = useState<{ width: number; height: number }>({ width: 0, height: 0 });
  const [viewState, setViewState] = useState<{ target: [number, number, number]; zoom: number }>({ target: [0, 0, 0], zoom: 0 });

  useEffect(() => {
    let cancelled = false;
    async function load() {
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
      const url = URL.createObjectURL(blob);
      const freqStart = Number(headers.get('X-Freq-Start') ?? f0 ?? 0);
      const freqEnd = Number(headers.get('X-Freq-End') ?? f1 ?? freqStart + 1);
      const timeStart = Number(headers.get('X-Time-Start') ?? t0 ?? 0);
      const timeEnd = Number(headers.get('X-Time-End') ?? t1 ?? timeStart + 1);
      setTile((current) => {
        if (current) {
          URL.revokeObjectURL(current.url);
        }
        return { url, bounds: [freqStart, timeStart, freqEnd, timeEnd] };
      });
    }
    load();
    return () => {
      cancelled = true;
      setTile((current) => {
        if (current) {
          URL.revokeObjectURL(current.url);
        }
        return null;
      });
    };
  }, [bandId, f0, f1, t0, t1, maxw, maxt]);

  // Observe container size for fitting
  useEffect(() => {
    if (!containerRef.current) return;
    const el = containerRef.current;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const cr = entry.contentRect;
        setContainerSize({ width: cr.width, height: cr.height });
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Fit-to-bounds when a new tile or size arrives
  useEffect(() => {
    if (!tile || containerSize.width <= 0 || containerSize.height <= 0) return;
    const [fx0, ty0, fx1, ty1] = tile.bounds;
    const worldW = Math.max(1e-6, Math.abs(fx1 - fx0));
    const worldH = Math.max(1e-6, Math.abs(ty1 - ty0));
    const scaleX = containerSize.width / worldW;
    const scaleY = containerSize.height / worldH;
    const scale = Math.max(1e-9, Math.min(scaleX, scaleY));
    const zoom = Math.log2(scale);
    const cx = fx0 + worldW / 2;
    const cy = ty0 + worldH / 2;
    setViewState({ target: [cx, cy, 0], zoom });
  }, [tile, containerSize]);

  const layer = useMemo(() => {
    if (!tile) return null;
    return new BitmapLayer({
      id: 'waterfall-bitmap',
      image: tile.url,
      bounds: tile.bounds,
      desaturate: 0,
      opacity: 1
    });
  }, [tile]);

  return (
    <div ref={containerRef} style={{ position: 'relative', height: '100%' }}>
      <DeckGL
        views={new OrthographicView({ flipY: true })}
        controller={{ dragPan: true, dragRotate: false, scrollZoom: true, doubleClickZoom: true }}
        viewState={viewState}
        onViewStateChange={(e) => setViewState(e.viewState as any)}
        style={{ width: '100%', height: '100%' }}
        layers={layer ? [layer] : []}
      />
      <div
        style={{
          position: 'absolute',
          right: 16,
          top: 16,
          width: 12,
          height: 160,
          background: 'linear-gradient(180deg, #fffbcc 0%, #1a1e2b 100%)',
          borderRadius: 6,
          border: '1px solid rgba(255,255,255,0.3)'
        }}
      />
    </div>
  );
}

export default Waterfall;
