import dynamic from 'next/dynamic';
import { useRouter } from 'next/router';
import { useEffect, useMemo, useState, useCallback } from 'react';
import type { Layout, PlotData } from 'plotly.js';

import { getBronzeBandSummary, getAssignments, createAssignment, deleteAssignment, type Assignment } from '../../../../../lib/api';

const Plot = dynamic(() => import('react-plotly.js'), { ssr: false });

type Status = 'idle' | 'loading' | 'error' | 'ready';

export default function FeatureBandDetailPage() {
  const router = useRouter();
  const { site, year, month, band_index } = router.query as { 
    site?: string; 
    year?: string; 
    month?: string; 
    band_index?: string;
  };
  const missionType = router.query.mission_type as string | undefined;
  const sensor = router.query.sensor as string | undefined;
  
  const [summary, setSummary] = useState<{ freq_hz: number; power_min: number; power_max: number; power_mean: number }[]>([]);
  const [bandLabel, setBandLabel] = useState<string | null>(null);
  const [startHz, setStartHz] = useState<number | null>(null);
  const [stopHz, setStopHz] = useState<number | null>(null);
  const [nTraces, setNTraces] = useState<number | null>(null);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [allAssignments, setAllAssignments] = useState<Assignment[]>([]);
  const [status, setStatus] = useState<Status>('idle');
  const [error, setError] = useState<string | null>(null);
  const [selectionMode, setSelectionMode] = useState<boolean>(false);
  const [showLabels, setShowLabels] = useState<boolean>(true);
  const [showAssignmentModal, setShowAssignmentModal] = useState<boolean>(false);
  const [selectedRange, setSelectedRange] = useState<{ f0: number; f1: number } | null>(null);
  const [assignmentForm, setAssignmentForm] = useState<{
    label: string;
    lat: number;
    long: number;
  }>({ label: '', lat: 0, long: 0 });
  const [savingAssignment, setSavingAssignment] = useState<boolean>(false);
  const [zoomRange, setZoomRange] = useState<[number, number] | undefined>(undefined);
  const [deletingAssignment, setDeletingAssignment] = useState<{ center_freq_hz: number; bandwidth_hz: number } | null>(null);

  useEffect(() => {
    if (!site || !year || !month || !band_index || !missionType || !sensor) return;

    const bandIdx = parseInt(band_index, 10);
    if (isNaN(bandIdx)) {
      setError('Invalid band_index');
      setStatus('error');
      return;
    }

    setStatus('loading');
    setError(null);

    // Load full bronze scan for per-frequency stats (use_feature=false)
    getBronzeBandSummary(bandIdx, {
      mission_type: missionType,
      site: site,
      sensor: sensor,
      year: year,
      month: month,
      use_feature: false, // Force full bronze scan for per-frequency breakdown
    })
      .then((bandSummary) => {
        if (!bandSummary.stats || bandSummary.stats.length === 0) {
          throw new Error('No per-frequency stats available from bronze scan');
        }
        setSummary(bandSummary.stats);
        setBandLabel(bandSummary.band_label || null);
        setStartHz(bandSummary.start_hz);
        setStopHz(bandSummary.stop_hz);
        setNTraces(bandSummary.n_traces);
        setStatus('ready');
        
        // Load assignments separately (don't block chart display if this fails)
        const monthStr = `${year}-${month}`;
        getAssignments(site, monthStr)
          .then((assignmentsData) => {
            // Store ALL assignments
            const all = assignmentsData.assignments || [];
            setAllAssignments(all);
            
            // Filter assignments to only those within band frequency range for display
            const bandStart = bandSummary.start_hz;
            const bandStop = bandSummary.stop_hz;
            const filtered = all.filter((assignment) => {
              const assignmentStart = assignment.center_freq_hz - assignment.bandwidth_hz / 2;
              const assignmentEnd = assignment.center_freq_hz + assignment.bandwidth_hz / 2;
              return assignmentStart < bandStop && assignmentEnd > bandStart;
            });
            setAssignments(filtered);
          })
          .catch((err: any) => {
            // If assignments file doesn't exist (404), just continue with empty array
            if (err?.message?.includes('404') || err?.message?.includes('not found')) {
              setAssignments([]);
            } else {
              // Log other errors but don't block the page
              console.error('Failed to load assignments:', err);
              setAssignments([]);
              setAllAssignments([]);
            }
          });
      })
      .catch((err: any) => {
        setError(err?.message ?? 'Failed to load band data');
        setStatus('error');
      });
  }, [site, year, month, band_index, missionType, sensor]);

  // Keyboard shortcut: Ctrl+M (Windows/Linux) or Cmd+M (Mac) to toggle selection mode
  useEffect(() => {
    if (status !== 'ready') return; // Only when page is ready
    
    const handleKeyPress = (event: KeyboardEvent) => {
      // Check for Ctrl+M (Windows/Linux) or Cmd+M (Mac)
      const isModifierPressed = event.ctrlKey || event.metaKey;
      if (isModifierPressed && (event.key === 'm' || event.key === 'M')) {
        // Don't trigger if user is typing in an input/textarea
        const target = event.target as HTMLElement;
        if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') {
          return;
        }
        
        event.preventDefault();
        setSelectionMode(prev => !prev);
      }
    };
    
    window.addEventListener('keydown', handleKeyPress);
    return () => {
      window.removeEventListener('keydown', handleKeyPress);
    };
  }, [status]);

  const traces = useMemo<PlotData[]>(() => {
    if (summary.length === 0) return [];
    
    const freqs = summary.map((s) => s.freq_hz / 1e6); // Convert to MHz
    const powerMin = summary.map((s) => s.power_min);
    const powerMax = summary.map((s) => s.power_max);
    const powerMean = summary.map((s) => s.power_mean);

    return [
      {
        x: freqs,
        y: powerMin,
        type: 'scatter',
        mode: 'lines',
        name: 'Min',
        line: { color: '#ff6b6b', width: 1.5 },
        hoverinfo: 'x+y+name',
      },
      {
        x: freqs,
        y: powerMean,
        type: 'scatter',
        mode: 'lines',
        name: 'Mean',
        line: { color: '#4ecdc4', width: 2 },
        hoverinfo: 'x+y+name',
      },
      {
        x: freqs,
        y: powerMax,
        type: 'scatter',
        mode: 'lines',
        name: 'Max',
        line: { color: '#ffa500', width: 1.5 },
        hoverinfo: 'x+y+name',
      },
    ];
  }, [summary]);

  const generateDefaultLabel = useCallback(() => {
    // Find all existing labels that match "Freq_N" pattern (use allAssignments to check all labels)
    const freqLabels = allAssignments
      .map((a: Assignment) => a.label)
      .filter((label: string) => /^Freq_\d+$/.test(label))
      .map((label: string) => {
        const match = label.match(/^Freq_(\d+)$/);
        return match ? parseInt(match[1], 10) : 0;
      });
    
    // Find next available number
    const nextNum = freqLabels.length > 0 
      ? Math.max(...freqLabels) + 1 
      : 1;
    
    return `Freq_${nextNum}`;
  }, [allAssignments]);

  const handlePlotSelection = useCallback((eventData: any) => {
    if (!selectionMode || !eventData) {
      return;
    }

    // Extract frequency range from selection
    // Plotly provides range in eventData.range for box selections
    let f0MHz: number;
    let f1MHz: number;

    if (eventData.range && eventData.range.x) {
      // Use range from box selection (more accurate)
      f0MHz = Math.min(eventData.range.x[0], eventData.range.x[1]);
      f1MHz = Math.max(eventData.range.x[0], eventData.range.x[1]);
    } else if (eventData.points && eventData.points.length > 0) {
      // Fallback to points if range not available
      const xValues = eventData.points.map((p: any) => p.x).filter((x: any) => x != null);
      if (xValues.length === 0) return;
      f0MHz = Math.min(...xValues);
      f1MHz = Math.max(...xValues);
    } else {
      return;
    }

    // Convert to Hz
    const f0Hz = f0MHz * 1e6;
    const f1Hz = f1MHz * 1e6;

    // Validate selection is within band bounds
    if (startHz !== null && stopHz !== null) {
      if (f0Hz < startHz || f1Hz > stopHz) {
        alert('Selection must be within the band frequency range');
        return;
      }
    }

    // Validate minimum bandwidth (1 kHz)
    const bandwidthHz = f1Hz - f0Hz;
    if (bandwidthHz < 1000) {
      alert('Selection must be at least 1 kHz wide');
      return;
    }

    setSelectedRange({ f0: f0Hz, f1: f1Hz });
    // Generate default label when opening modal
    const defaultLabel = generateDefaultLabel();
    setAssignmentForm({ label: defaultLabel, lat: 0, long: 0 });
    setShowAssignmentModal(true);
  }, [selectionMode, startHz, stopHz, generateDefaultLabel]);

  const ensureUniqueLabel = useCallback((label: string): string => {
    // Use allAssignments to check uniqueness across all assignments, not just filtered ones
    const existingLabels = allAssignments.map((a: Assignment) => a.label);
    
    if (!existingLabels.includes(label)) {
      return label; // Already unique
    }
    
    // Try appending _1, _2, etc.
    let counter = 1;
    let newLabel = `${label}_${counter}`;
    while (existingLabels.includes(newLabel)) {
      counter++;
      newLabel = `${label}_${counter}`;
    }
    
    return newLabel;
  }, [allAssignments]);

  const handleRelayout = useCallback((event: any) => {
    // Track zoom changes from Plotly
    const xAuto = event['xaxis.autorange'];
    if (xAuto === true) {
      // User reset zoom (double-click)
      setZoomRange(undefined);
      return;
    }
    const x0 = event['xaxis.range[0]'];
    const x1 = event['xaxis.range[1]'];
    if (typeof x0 === 'number' && typeof x1 === 'number') {
      // User zoomed/panned - store the range
      setZoomRange([x0, x1]);
    }
  }, []);

  // Helper function to format number with max 3 decimal places, removing trailing zeros
  const formatNumber = (value: number, maxDecimals: number = 3): string => {
    // Round to maxDecimals places and remove trailing zeros
    const rounded = value.toFixed(maxDecimals);
    // Remove trailing zeros and decimal point if not needed
    return parseFloat(rounded).toString();
  };

  // Helper function to format center frequency (auto: MHz if < 10 GHz, GHz if >= 10 GHz)
  const formatCenterFreq = (freqHz: number): string => {
    if (freqHz >= 10e9) {
      return `${formatNumber(freqHz / 1e9)} GHz`;
    } else {
      return `${formatNumber(freqHz / 1e6)} MHz`;
    }
  };

  // Helper function to format bandwidth (auto: MHz if >= 1 MHz, kHz if < 1 MHz)
  const formatBandwidth = (bwHz: number): string => {
    if (bwHz >= 1e6) {
      return `${formatNumber(bwHz / 1e6)} MHz`;
    } else {
      return `${formatNumber(bwHz / 1e3)} kHz`;
    }
  };

  const handleExportAssignments = useCallback(() => {
    if (allAssignments.length === 0) return;
    
    // CSV header - use readable units in column names
    const headers = ['lat', 'long', 'center_freq', 'bandwidth', 'label'];
    
    // CSV rows - use allAssignments to export all assignments, not just filtered ones
    // Format frequencies with appropriate units
    const rows = allAssignments.map((a: Assignment) => [
      a.lat.toString(),
      a.long.toString(),
      formatCenterFreq(a.center_freq_hz),
      formatBandwidth(a.bandwidth_hz),
      a.label
    ]);
    
    // Combine header and rows (escape quotes in cell values)
    const escapeCSV = (value: string) => {
      if (value.includes(',') || value.includes('"') || value.includes('\n')) {
        return `"${value.replace(/"/g, '""')}"`;
      }
      return value;
    };
    
    const csvContent = [
      headers.join(','),
      ...rows.map((row: string[]) => row.map((cell: string) => escapeCSV(cell)).join(','))
    ].join('\n');
    
    // Create blob and download
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    const monthStr = `${year}-${month}`;
    link.download = `assignments_${site}_${monthStr}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }, [allAssignments, site, year, month]);

  const handleDeleteAssignment = useCallback(async (assignment: Assignment) => {
    if (!site || !year || !month) return;
    
    if (!confirm(`Are you sure you want to delete assignment "${assignment.label || 'Unlabeled'}"?`)) {
      return;
    }

    setDeletingAssignment({ center_freq_hz: assignment.center_freq_hz, bandwidth_hz: assignment.bandwidth_hz });
    const monthStr = `${year}-${month}`;

    try {
      const result = await deleteAssignment(site, monthStr, {
        center_freq_hz: assignment.center_freq_hz,
        bandwidth_hz: assignment.bandwidth_hz,
      });
      
      // Store ALL assignments
      const all = result.assignments || [];
      setAllAssignments(all);
      
      // Filter assignments to only those within band frequency range for display
      if (startHz !== null && stopHz !== null) {
        const filtered = all.filter((a) => {
          const assignmentStart = a.center_freq_hz - a.bandwidth_hz / 2;
          const assignmentEnd = a.center_freq_hz + a.bandwidth_hz / 2;
          return assignmentStart < stopHz && assignmentEnd > startHz;
        });
        setAssignments(filtered);
      } else {
        setAssignments(all);
      }
    } catch (err: any) {
      alert(`Failed to delete assignment: ${err?.message || 'Unknown error'}`);
    } finally {
      setDeletingAssignment(null);
    }
  }, [site, year, month, startHz, stopHz]);

  const handleSaveAssignment = useCallback(async () => {
    if (!selectedRange || !assignmentForm.label.trim()) {
      alert('Please provide a label for the assignment');
      return;
    }

    if (!site || !year || !month) return;

    setSavingAssignment(true);
    const monthStr = `${year}-${month}`;
    const centerFreqHz = (selectedRange.f0 + selectedRange.f1) / 2;
    const bandwidthHz = selectedRange.f1 - selectedRange.f0;

    try {
      // Ensure label is unique
      const uniqueLabel = ensureUniqueLabel(assignmentForm.label.trim());
      
      const newAssignment: Assignment = {
        lat: assignmentForm.lat,
        long: assignmentForm.long,
        center_freq_hz: centerFreqHz,
        bandwidth_hz: bandwidthHz,
        label: uniqueLabel,
      };

      const result = await createAssignment(site, monthStr, newAssignment);
      
      // Store ALL assignments
      const all = result.assignments || [];
      setAllAssignments(all);
      
      // Filter assignments to only those within band frequency range for display
      if (startHz !== null && stopHz !== null) {
        const filtered = all.filter((assignment) => {
          const assignmentStart = assignment.center_freq_hz - assignment.bandwidth_hz / 2;
          const assignmentEnd = assignment.center_freq_hz + assignment.bandwidth_hz / 2;
          return assignmentStart < stopHz && assignmentEnd > startHz;
        });
        setAssignments(filtered);
      } else {
        setAssignments(all);
      }

      setShowAssignmentModal(false);
      setSelectedRange(null);
      setAssignmentForm({ label: '', lat: 0, long: 0 });
      setSelectionMode(false);
    } catch (err: any) {
      alert(`Failed to save assignment: ${err?.message || 'Unknown error'}`);
    } finally {
      setSavingAssignment(false);
    }
  }, [selectedRange, assignmentForm, site, year, month, startHz, stopHz, ensureUniqueLabel]);

  const layout = useMemo<Partial<Layout>>(() => {
    // Create shapes and annotations for assignments
    const shapes: any[] = [];
    const annotations: any[] = [];

    assignments.forEach((assignment, idx) => {
      const centerFreqMHz = assignment.center_freq_hz / 1e6;
      const halfBandwidthMHz = assignment.bandwidth_hz / 2e6;
      const startFreqMHz = centerFreqMHz - halfBandwidthMHz;
      const endFreqMHz = centerFreqMHz + halfBandwidthMHz;

      // Add shaded region for bandwidth
      shapes.push({
        type: 'rect',
        xref: 'x',
        yref: 'paper',
        x0: startFreqMHz,
        x1: endFreqMHz,
        y0: 0,
        y1: 1,
        line: { width: 0 },
        fillcolor: `rgba(255, 215, 0, ${0.15 + (idx % 3) * 0.05})`, // Varying opacity
        opacity: 0.3,
      });

      // Add vertical line at center frequency
      shapes.push({
        type: 'line',
        xref: 'x',
        yref: 'paper',
        x0: centerFreqMHz,
        x1: centerFreqMHz,
        y0: 0,
        y1: 1,
        line: {
          color: '#ffd700',
          width: 2,
          dash: 'dot',
        },
      });

      // Add annotation with label (only if showLabels is true)
      if (showLabels) {
        annotations.push({
          x: centerFreqMHz,
          y: 0.95 - (idx % 3) * 0.03, // Position within visible area, stagger slightly
          xref: 'x',
          yref: 'paper',
          xanchor: 'center',
          yanchor: 'bottom',
          text: assignment.label || `Assignment ${idx + 1}`,
          showarrow: true,
          arrowhead: 2,
          arrowsize: 1,
          arrowwidth: 1.5,
          arrowcolor: '#ffd700',
          ax: 0,
          ay: -20,
          bgcolor: 'rgba(255, 215, 0, 0.8)',
          bordercolor: '#ffd700',
          borderwidth: 1,
          font: { color: '#000', size: 11 },
        });
      }
    });

    return {
      title: `Band ${band_index}${bandLabel ? ` (${bandLabel})` : ''} — Power Statistics`,
      dragmode: selectionMode ? 'select' : 'zoom',
      margin: { l: 64, r: 32, t: 80, b: 72 },
      paper_bgcolor: '#0c0d10',
      plot_bgcolor: '#0c0d10',
      font: { color: '#f7f7f7' },
      xaxis: {
        title: 'Frequency (MHz)',
        range: zoomRange,
        showline: true,
        mirror: true,
        ticks: 'outside',
        tickcolor: '#888',
        ticklen: 6,
        tickwidth: 1,
        automargin: true,
      },
      yaxis: {
        title: 'Power (dBm)',
        autorange: true,
        zeroline: false,
        showline: true,
        mirror: true,
        automargin: true,
      },
      shapes,
      annotations,
      showlegend: true,
      legend: {
        orientation: 'h',
        x: 0,
        y: 1.12,
        xanchor: 'left',
        yanchor: 'bottom',
        bgcolor: 'rgba(0,0,0,0)',
      },
    };
  }, [assignments, band_index, bandLabel, selectionMode, zoomRange, showLabels]);

  if (!site || !year || !month || !band_index || !missionType || !sensor) {
    return (
      <main className="app-shell">
        <p>Loading...</p>
      </main>
    );
  }

  if (status === 'loading') {
    return (
      <main className="app-shell">
        <p>Loading band data...</p>
      </main>
    );
  }

  if (status === 'error') {
    return (
      <main className="app-shell">
        <header className="app-header">
          <h1>Error</h1>
          <p className="error">{error || 'Failed to load band data'}</p>
        </header>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">Band Detail</p>
          <h1>
            Band {band_index}
            {bandLabel && ` — ${bandLabel}`}
          </h1>
          <p className="muted">
            Site: {site} | Year: {year} | Month: {month} | Mission: {missionType} | Sensor: {sensor}
            {startHz !== null && stopHz !== null && (
              <>
                <br />
                Frequency: {(startHz / 1e6).toFixed(3)} - {(stopHz / 1e6).toFixed(3)} MHz | Traces: {nTraces}
              </>
            )}
          </p>
        </div>
      </header>

      <section style={{ margin: '2rem 0' }}>
        <div style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
          <button
            type="button"
            onClick={() => setSelectionMode(!selectionMode)}
            style={{
              padding: '0.5rem 1rem',
              backgroundColor: selectionMode ? '#4ecdc4' : '#1a1b1f',
              color: '#f7f7f7',
              border: '1px solid rgba(255,255,255,0.15)',
              borderRadius: '4px',
              cursor: 'pointer',
            }}
          >
            {selectionMode ? '✓ Selection Mode Active' : 'Select Frequency Range'}
          </button>
          <button
            type="button"
            onClick={() => setShowLabels(!showLabels)}
            style={{
              padding: '0.5rem 1rem',
              backgroundColor: showLabels ? '#4ecdc4' : '#1a1b1f',
              color: '#f7f7f7',
              border: '1px solid rgba(255,255,255,0.15)',
              borderRadius: '4px',
              cursor: 'pointer',
            }}
          >
            {showLabels ? '✓ Labels: On' : 'Labels: Off'}
          </button>
          {selectionMode && (
            <p className="muted" style={{ margin: 0 }}>
              Drag on the chart to select a frequency range for a new assignment
            </p>
          )}
        </div>
        {traces.length > 0 && (
          <Plot
            data={traces}
            layout={layout}
            style={{ width: '100%', height: '600px', display: 'block' }}
            useResizeHandler
            config={{ displaylogo: false, responsive: true }}
            onSelected={handlePlotSelection}
            onRelayout={handleRelayout}
          />
        )}
      </section>

      {showAssignmentModal && selectedRange && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.7)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() => {
            if (!savingAssignment) {
              setShowAssignmentModal(false);
              setSelectedRange(null);
              setAssignmentForm({ label: '', lat: 0, long: 0 });
            }
          }}
        >
          <div
            style={{
              backgroundColor: '#1a1b1f',
              padding: '2rem',
              borderRadius: '8px',
              maxWidth: '500px',
              width: '90%',
              border: '1px solid rgba(255,255,255,0.15)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 style={{ marginTop: 0, color: '#f7f7f7' }}>Create Assignment</h2>
            <div style={{ marginBottom: '1rem' }}>
              <p className="muted" style={{ margin: '0.5rem 0' }}>
                Center Frequency: {(selectedRange.f0 / 1e6 + selectedRange.f1 / 1e6) / 2} MHz
              </p>
              <p className="muted" style={{ margin: '0.5rem 0' }}>
                Bandwidth: {(selectedRange.f1 - selectedRange.f0) / 1e6} MHz
              </p>
            </div>
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', marginBottom: '0.5rem', color: '#f7f7f7' }}>
                Label <span style={{ color: '#ff6b6b' }}>*</span>
              </label>
              <input
                type="text"
                value={assignmentForm.label}
                onChange={(e) => setAssignmentForm({ ...assignmentForm, label: e.target.value })}
                style={{
                  width: '100%',
                  padding: '0.5rem',
                  backgroundColor: '#0c0d10',
                  color: '#f7f7f7',
                  border: '1px solid rgba(255,255,255,0.15)',
                  borderRadius: '4px',
                }}
                placeholder="Enter assignment label"
                autoFocus
              />
            </div>
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', marginBottom: '0.5rem', color: '#f7f7f7' }}>
                Latitude (optional)
              </label>
              <input
                type="number"
                value={assignmentForm.lat}
                onChange={(e) => setAssignmentForm({ ...assignmentForm, lat: parseFloat(e.target.value) || 0 })}
                style={{
                  width: '100%',
                  padding: '0.5rem',
                  backgroundColor: '#0c0d10',
                  color: '#f7f7f7',
                  border: '1px solid rgba(255,255,255,0.15)',
                  borderRadius: '4px',
                }}
                step="0.000001"
              />
            </div>
            <div style={{ marginBottom: '1.5rem' }}>
              <label style={{ display: 'block', marginBottom: '0.5rem', color: '#f7f7f7' }}>
                Longitude (optional)
              </label>
              <input
                type="number"
                value={assignmentForm.long}
                onChange={(e) => setAssignmentForm({ ...assignmentForm, long: parseFloat(e.target.value) || 0 })}
                style={{
                  width: '100%',
                  padding: '0.5rem',
                  backgroundColor: '#0c0d10',
                  color: '#f7f7f7',
                  border: '1px solid rgba(255,255,255,0.15)',
                  borderRadius: '4px',
                }}
                step="0.000001"
              />
            </div>
            <div style={{ display: 'flex', gap: '1rem', justifyContent: 'flex-end' }}>
              <button
                type="button"
                onClick={() => {
                  setShowAssignmentModal(false);
                  setSelectedRange(null);
                  setAssignmentForm({ label: '', lat: 0, long: 0 });
                }}
                disabled={savingAssignment}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: 'transparent',
                  color: '#f7f7f7',
                  border: '1px solid rgba(255,255,255,0.15)',
                  borderRadius: '4px',
                  cursor: savingAssignment ? 'not-allowed' : 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSaveAssignment}
                disabled={savingAssignment || !assignmentForm.label.trim()}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: savingAssignment ? '#666' : '#4ecdc4',
                  color: '#000',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: savingAssignment || !assignmentForm.label.trim() ? 'not-allowed' : 'pointer',
                  fontWeight: 'bold',
                }}
              >
                {savingAssignment ? 'Saving...' : 'Save Assignment'}
              </button>
            </div>
          </div>
        </div>
      )}

      {assignments.length > 0 && (
        <section style={{ margin: '2rem 0', padding: '1rem', backgroundColor: '#1a1b1f', borderRadius: '8px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h2 style={{ marginTop: 0, marginBottom: 0 }}>Assignments ({assignments.length})</h2>
            <button
              type="button"
              onClick={handleExportAssignments}
              style={{
                padding: '0.5rem 1rem',
                backgroundColor: '#4ecdc4',
                color: '#000',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontWeight: 'bold',
              }}
            >
              Export CSV
            </button>
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #333' }}>
                <th style={{ textAlign: 'left', padding: '0.5rem' }}>Label</th>
                <th style={{ textAlign: 'left', padding: '0.5rem' }}>Center Freq (MHz)</th>
                <th style={{ textAlign: 'left', padding: '0.5rem' }}>Bandwidth (MHz)</th>
                <th style={{ textAlign: 'left', padding: '0.5rem' }}>Lat</th>
                <th style={{ textAlign: 'left', padding: '0.5rem' }}>Long</th>
                <th style={{ textAlign: 'left', padding: '0.5rem', width: '80px' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {assignments.map((assignment, idx) => {
                const isDeleting = deletingAssignment && 
                  Math.abs(deletingAssignment.center_freq_hz - assignment.center_freq_hz) < 1e-6 &&
                  Math.abs(deletingAssignment.bandwidth_hz - assignment.bandwidth_hz) < 1e-6;
                return (
                  <tr key={idx} style={{ borderBottom: '1px solid #222' }}>
                    <td style={{ padding: '0.5rem' }}>{assignment.label || '—'}</td>
                    <td style={{ padding: '0.5rem' }}>{(assignment.center_freq_hz / 1e6).toFixed(6)}</td>
                    <td style={{ padding: '0.5rem' }}>{(assignment.bandwidth_hz / 1e6).toFixed(6)}</td>
                    <td style={{ padding: '0.5rem' }}>{assignment.lat.toFixed(6)}</td>
                    <td style={{ padding: '0.5rem' }}>{assignment.long.toFixed(6)}</td>
                    <td style={{ padding: '0.5rem' }}>
                      <button
                        type="button"
                        onClick={() => handleDeleteAssignment(assignment)}
                        disabled={isDeleting}
                        style={{
                          padding: '0.25rem 0.5rem',
                          backgroundColor: isDeleting ? '#666' : '#ff6b6b',
                          color: '#fff',
                          border: 'none',
                          borderRadius: '4px',
                          cursor: isDeleting ? 'not-allowed' : 'pointer',
                          fontSize: '0.85em',
                        }}
                        title="Delete assignment"
                      >
                        {isDeleting ? 'Deleting...' : 'Delete'}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      )}

      {assignments.length === 0 && status === 'ready' && (
        <section style={{ margin: '2rem 0', padding: '1rem', backgroundColor: '#1a1b1f', borderRadius: '8px' }}>
          <p className="muted">No assignments found for this site/month. Upload a CSV file from the feature page.</p>
        </section>
      )}
    </main>
  );
}

