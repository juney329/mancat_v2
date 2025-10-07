import { useEffect, useMemo, useState } from 'react';
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

  const initialViewState = useMemo(
    () => ({
      target: [
        (tile?.bounds[0] ?? f0 ?? 0) + ((tile?.bounds[2] ?? f1 ?? 1) - (tile?.bounds[0] ?? f0 ?? 0)) / 2,
        (tile?.bounds[1] ?? t0 ?? 0) + ((tile?.bounds[3] ?? t1 ?? 1) - (tile?.bounds[1] ?? t0 ?? 0)) / 2,
        0
      ],
      zoom: 0
    }),
    [tile, f0, f1, t0, t1]
  );

  return (
    <div style={{ position: 'relative' }}>
      <DeckGL
        views={new OrthographicView({ flipY: true })}
        controller={{ dragPan: true, dragRotate: false }}
        initialViewState={initialViewState}
        style={{ width: '100%', height: '400px' }}
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
