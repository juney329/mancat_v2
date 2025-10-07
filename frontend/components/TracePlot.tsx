import dynamic from 'next/dynamic';
import { useCallback, useMemo } from 'react';
import type { Layout, PlotData } from 'plotly.js';

import type { Marker, PeakItem } from '../lib/api';

const Plot = dynamic(() => import('react-plotly.js'), { ssr: false });

export interface TracePlotProps {
  freqs: number[];
  curves: Record<string, number[]>;
  peaks?: PeakItem[];
  markers?: Marker[];
  onZoom?: (range: { f0: number; f1: number }) => void;
}

export function TracePlot({ freqs, curves, peaks = [], markers = [], onZoom }: TracePlotProps) {
  const traces = useMemo(() => {
    const base: PlotData[] = Object.entries(curves).map(([name, values]) => ({
      x: freqs,
      y: values,
      type: 'scatter',
      mode: 'lines',
      name,
      hoverinfo: 'x+y+name'
    }));

    if (peaks.length > 0) {
      base.push({
        x: peaks.map((peak) => peak.freq),
        y: peaks.map((peak) => peak.value),
        type: 'scatter',
        mode: 'markers',
        name: 'Peaks',
        marker: { color: '#ffcc00', size: 8 },
        hoverinfo: 'x+y+text',
        text: peaks.map((peak) => `Prominence: ${peak.properties.prominences ?? ''}`)
      });
    }

    return base;
  }, [curves, freqs, peaks]);

  const layout = useMemo<Partial<Layout>>(() => {
    const shapes = markers.map((marker) => {
      if (marker.width && marker.width > 0) {
        return {
          type: 'rect',
          xref: 'x',
          yref: 'paper',
          x0: marker.freq - marker.width / 2,
          x1: marker.freq + marker.width / 2,
          y0: 0,
          y1: 1,
          line: { width: 0 },
          fillcolor: marker.color ?? 'rgba(255, 0, 0, 0.2)' ,
          opacity: 0.3
        };
      }
      return {
        type: 'line',
        xref: 'x',
        yref: 'paper',
        x0: marker.freq,
        x1: marker.freq,
        y0: 0,
        y1: 1,
        line: {
          color: marker.color ?? '#ff0000',
          width: 2,
          dash: 'dot'
        }
      };
    });

    return {
      dragmode: 'zoom',
      margin: { l: 50, r: 20, t: 30, b: 40 },
      paper_bgcolor: '#0c0d10',
      plot_bgcolor: '#0c0d10',
      font: { color: '#f7f7f7' },
      xaxis: { title: 'Frequency (Hz)' },
      yaxis: { title: 'Power (dB)' },
      shapes,
      showlegend: true
    } satisfies Partial<Layout>;
  }, [markers]);

  const handleRelayout = useCallback(
    (event: Partial<Layout>) => {
      const x0 = (event as any)['xaxis.range[0]'];
      const x1 = (event as any)['xaxis.range[1]'];
      if (onZoom && typeof x0 === 'number' && typeof x1 === 'number') {
        onZoom({ f0: x0, f1: x1 });
      }
    },
    [onZoom]
  );

  return (
    <Plot
      data={traces}
      layout={layout}
      style={{ width: '100%', height: '100%' }}
      onRelayout={handleRelayout}
      config={{ displaylogo: false, responsive: true }}
    />
  );
}

export default TracePlot;
