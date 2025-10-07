export interface BandMeta {
  id: string;
  meta: Record<string, unknown>;
}

export type SummaryResponse = Record<string, number[]> & { freqs: number[] };

export interface PeakRequest {
  curve: string;
  height?: number;
  prominence?: number;
  distance?: number;
  f0?: number;
  f1?: number;
}

export interface PeakItem {
  freq: number;
  value: number;
  properties: Record<string, number>;
}

export interface MarkersPayload {
  markers: Marker[];
}

export interface Marker {
  id: string;
  freq: number;
  label?: string;
  color?: string;
  width?: number;
}

export interface PlaybackTick {
  t0: number;
  t1: number;
  cursor_unix: number;
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000';

export async function fetchJSON<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function getBands(): Promise<BandMeta[]> {
  return fetchJSON<BandMeta[]>('/bands');
}

export async function getBandMeta(id: string): Promise<Record<string, unknown>> {
  return fetchJSON<Record<string, unknown>>(`/bands/${id}/meta`);
}

export async function getSummary(
  id: string,
  params: { f0?: number; f1?: number; max_pts?: number } = {}
): Promise<SummaryResponse> {
  const query = new URLSearchParams();
  if (params.f0 !== undefined) query.set('f0', params.f0.toString());
  if (params.f1 !== undefined) query.set('f1', params.f1.toString());
  if (params.max_pts !== undefined) query.set('max_pts', params.max_pts.toString());
  const url = `/bands/${id}/summary${query.toString() ? `?${query}` : ''}`;
  return fetchJSON<SummaryResponse>(url);
}

export interface WaterfallTileResponse {
  blob: Blob;
  headers: Headers;
}

export async function getWaterfallTile(
  id: string,
  params: { f0?: number; f1?: number; t0?: number; t1?: number; maxw?: number; maxt?: number; fmt?: string } = {}
): Promise<WaterfallTileResponse> {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined) query.set(key, String(value));
  });
  const response = await fetch(
    `${API_BASE}/bands/${id}/waterfall_tile${query.toString() ? `?${query}` : ''}`
  );
  if (!response.ok) {
    throw new Error('Failed to fetch waterfall tile');
  }
  const blob = await response.blob();
  return { blob, headers: response.headers };
}

export async function postPeaks(id: string, payload: PeakRequest): Promise<PeakItem[]> {
  const response = await fetch(`${API_BASE}/bands/${id}/peaks`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error('Failed to detect peaks');
  }
  const data = (await response.json()) as { peaks: PeakItem[] };
  return data.peaks;
}

export async function getMarkers(id: string): Promise<Marker[]> {
  const payload = await fetchJSON<MarkersPayload>(`/bands/${id}/markers`);
  return payload.markers;
}

export async function saveMarkers(id: string, markers: Marker[]): Promise<Marker[]> {
  const response = await fetch(`${API_BASE}/bands/${id}/markers`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ markers })
  });
  if (!response.ok) {
    throw new Error('Failed to save markers');
  }
  const payload = (await response.json()) as MarkersPayload;
  return payload.markers;
}

export function createPlaybackSocket(
  id: string,
  params: { window_s?: number; fps?: number } = {}
): WebSocket {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined) query.set(key, String(value));
  });
  const wsUrl = new URL(`${API_BASE.replace(/^http/, 'ws')}/ws/bands/${id}`);
  if ([...query.keys()].length) {
    wsUrl.search = query.toString();
  }
  return new WebSocket(wsUrl.toString());
}
