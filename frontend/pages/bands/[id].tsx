import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/router';

import TracePlot from '../../components/TracePlot';
import Waterfall from '../../components/Waterfall';
import PeakControls from '../../components/PeakControls';
import PlaybackBar from '../../components/PlaybackBar';
import MarkersPanel from '../../components/MarkersPanel';
import type { Marker, PeakItem, PlaybackTick, SummaryResponse } from '../../lib/api';
import { getMarkers, getSummary, saveMarkers } from '../../lib/api';

export default function BandDetailPage() {
  const router = useRouter();
  const { id } = router.query as { id?: string };
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [peaks, setPeaks] = useState<PeakItem[]>([]);
  const [markers, setMarkers] = useState<Marker[]>([]);
  const [freqWindow, setFreqWindow] = useState<{ f0?: number; f1?: number }>({});
  const [timeWindow, setTimeWindow] = useState<{ t0?: number; t1?: number }>({});

  useEffect(() => {
    if (!id) return;
    getSummary(id, { max_pts: 1200 })
      .then((data) => {
        setSummary(data);
        const start = data.freqs.length > 0 ? data.freqs[0] : undefined;
        const end = data.freqs.length > 0 ? data.freqs[data.freqs.length - 1] : start;
        setFreqWindow({ f0: start, f1: end });
      })
      .catch((error) => console.error('Failed to load summary', error));
    getMarkers(id)
      .then(setMarkers)
      .catch((error) => console.error('Failed to load markers', error));
  }, [id]);

  const curves = useMemo<Record<string, number[]>>(() => {
    if (!summary) return {};
    const { freqs, ...rest } = summary;
    return rest as Record<string, number[]>;
  }, [summary]);

  const handleZoom = useCallback(
    (range: { f0: number; f1: number }) => {
      if (!id) return;
      setFreqWindow(range);
      getSummary(id, { f0: range.f0, f1: range.f1, max_pts: 1200 })
        .then((data) => setSummary(data))
        .catch((error) => console.error('Failed to update summary', error));
    },
    [id]
  );

  const handlePlaybackTick = useCallback((tick: PlaybackTick) => {
    setTimeWindow({ t0: tick.t0, t1: tick.t1 });
  }, []);

  const handleCreateMarker = useCallback(
    (marker: Marker) => {
      if (!id) return;
      const updated = [...markers.filter((m) => m.id !== marker.id), marker];
      saveMarkers(id, updated)
        .then(setMarkers)
        .catch((error) => console.error('Failed to save markers', error));
    },
    [id, markers]
  );

  const handleDeleteMarker = useCallback(
    (markerId: string) => {
      if (!id) return;
      const updated = markers.filter((marker) => marker.id !== markerId);
      saveMarkers(id, updated)
        .then(setMarkers)
        .catch((error) => console.error('Failed to save markers', error));
    },
    [id, markers]
  );

  if (!id) {
    return <main>Loading…</main>;
  }

  if (!summary) {
    return <main>Loading summary…</main>;
  }

  return (
    <main>
      <h1>Band {id}</h1>
      <section>
        <PlaybackBar bandId={id} onTick={handlePlaybackTick} />
      </section>
      <section>
        <TracePlot freqs={summary.freqs} curves={curves} peaks={peaks} markers={markers} onZoom={handleZoom} />
      </section>
      <section>
        <PeakControls
          bandId={id}
          curves={Object.keys(curves)}
          freqWindow={freqWindow}
          onPeaks={setPeaks}
        />
      </section>
      <section>
        <Waterfall bandId={id} f0={freqWindow.f0} f1={freqWindow.f1} t0={timeWindow.t0} t1={timeWindow.t1} />
      </section>
      <section>
        <MarkersPanel markers={markers} onCreate={handleCreateMarker} onDelete={handleDeleteMarker} />
      </section>
    </main>
  );
}
