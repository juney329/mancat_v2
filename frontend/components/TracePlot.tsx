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
  xRange?: { f0: number; f1: number } | null;
}

export function TracePlot({ freqs, curves, peaks = [], markers = [], onZoom, xRange }: TracePlotProps) {
  // Compute a safe x-range intersected with data domain to avoid empty axis
  const safeXRange = useMemo(() => {
    if (!freqs || freqs.length === 0) return undefined;
    const domainMin = freqs[0];
    const domainMax = freqs[freqs.length - 1];
    if (!xRange) return undefined;
    const f0 = Math.max(domainMin, Math.min(domainMax, xRange.f0));
    const f1 = Math.max(domainMin, Math.min(domainMax, xRange.f1));
    if (f1 <= f0) return [domainMin, domainMax] as [number, number];
    return [f0, f1] as [number, number];
  }, [freqs, xRange]);
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
      margin: { l: 56, r: 24, t: 64, b: 72 },
      paper_bgcolor: '#0c0d10',
      plot_bgcolor: '#0c0d10',
      font: { color: '#f7f7f7' },
      xaxis: {
        title: 'Frequency (Hz)',
        range: safeXRange,
        showline: true,
        mirror: true,
        ticks: 'outside',
        tickcolor: '#888',
        ticklen: 6,
        tickwidth: 1,
        tickformat: '~s',
        automargin: true
      },
      yaxis: {
        title: 'Power (dB)',
        autorange: true,
        zeroline: false,
        showline: true,
        mirror: true,
        automargin: true
      },
      shapes,
      showlegend: true,
      legend: {
        orientation: 'h',
        x: 0,
        y: 1.08,
        xanchor: 'left',
        yanchor: 'bottom',
        bgcolor: 'rgba(0,0,0,0)'
      }
    } satisfies Partial<Layout>;
  }, [markers, safeXRange]);

  const handleRelayout = useCallback(
    (event: Partial<Layout>) => {
      const xAuto = (event as any)['xaxis.autorange'];
      if (onZoom && xAuto === true && Array.isArray(freqs) && freqs.length > 1) {
        onZoom({ f0: freqs[0], f1: freqs[freqs.length - 1] });
        return;
      }
      const x0 = (event as any)['xaxis.range[0]'];
      const x1 = (event as any)['xaxis.range[1]'];
      if (onZoom && typeof x0 === 'number' && typeof x1 === 'number') {
        onZoom({ f0: x0, f1: x1 });
      }
    },
    [onZoom, freqs]
  );

  return (
    <Plot
      data={traces}
      layout={layout}
      style={{ width: '100%', height: '520px', display: 'block' }}
      useResizeHandler
      onRelayout={handleRelayout}
      config={{ displaylogo: false, responsive: true }}
    />
  );
}

export default TracePlot;
