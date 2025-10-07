import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/router';

import { BandMeta, getBands } from '../lib/api';

export interface BandsSidebarProps {
  onSelect?: (id: string) => void;
}

export function BandsSidebar({ onSelect }: BandsSidebarProps) {
  const router = useRouter();
  const currentId = (router.query?.id as string | undefined) ?? undefined;
  const [bands, setBands] = useState<BandMeta[]>([]);

  useEffect(() => {
    getBands()
      .then(setBands)
      .catch((err) => console.error('Failed to load bands', err));
  }, []);

  const items = useMemo(() => bands.sort((a, b) => String(a.id).localeCompare(String(b.id))), [bands]);

  function formatRange(meta: Record<string, unknown> | undefined): string | null {
    if (!meta) return null;
    const start = Number((meta as any).f_start);
    const stop = Number((meta as any).f_stop);
    if (!Number.isFinite(start) || !Number.isFinite(stop)) return null;
    if (start >= 1_000_000_000 && stop >= 1_000_000_000) {
      const s = Math.round(start / 1_000_000_000);
      const e = Math.round(stop / 1_000_000_000);
      return `${s} - ${e} GHz`;
    }
    const s = Math.round(start / 1_000_000);
    const e = Math.round(stop / 1_000_000);
    return `${s} - ${e} MHz`;
  }

  return (
    <aside
      style={{
        width: 280,
        minWidth: 240,
        maxWidth: 320,
        height: '100vh',
        position: 'sticky',
        top: 0,
        overflowY: 'auto',
        background: '#0c0d10',
        borderRight: '1px solid rgba(255,255,255,0.08)',
        padding: '1rem'
      }}
    >
      <h2 style={{ margin: '0 0 0.5rem 0' }}>Bands</h2>
      <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: '0.5rem' }}>
        {items.map((band) => {
          const id = String((band as any).id ?? band.id);
          const active = currentId === id;
          const label = formatRange((band as any).meta) ?? `Band ${id}`;
          return (
            <li key={id}>
              <Link
                href={`/bands/${id}`}
                onClick={() => onSelect?.(id)}
                style={{
                  display: 'block',
                  padding: '0.5rem 0.75rem',
                  borderRadius: 8,
                  textDecoration: 'none',
                  background: active ? 'rgba(255,255,255,0.08)' : 'transparent',
                  color: '#f7f7f7',
                  border: '1px solid rgba(255,255,255,0.08)'
                }}
              >
                {label}
              </Link>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}

export default BandsSidebar;


