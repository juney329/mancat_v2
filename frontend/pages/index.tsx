import Link from 'next/link';
import { useEffect, useState } from 'react';

import type { BandMeta } from '../lib/api';
import { getBands } from '../lib/api';

export default function IndexPage() {
  const [bands, setBands] = useState<BandMeta[]>([]);

  useEffect(() => {
    getBands().then(setBands).catch((error) => {
      console.error('Failed to load bands', error);
    });
  }, []);

  return (
    <main>
      <h1>RF Spectrum Bands</h1>
      <p>Select a band to explore summary traces and waterfall heatmaps.</p>
      <ul style={{ display: 'grid', gap: '1rem', listStyle: 'none', padding: 0 }}>
        {bands.map((band) => (
          <li key={band.id} style={{ background: '#1a1e2b', padding: '1rem', borderRadius: '0.75rem' }}>
            <h2 style={{ marginTop: 0 }}>{band.id}</h2>
            <pre style={{ whiteSpace: 'pre-wrap', fontSize: '0.8rem' }}>
              {JSON.stringify(band.meta, null, 2)}
            </pre>
            <Link href={`/bands/${band.id}`}>Open Band</Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
