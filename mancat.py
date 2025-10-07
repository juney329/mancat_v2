#!/usr/bin/env python3
"""
mancat.py — Batch processor per SPEC

This CLI merges CRFS .pbd2 chunks and writes per-band artifacts:
- waterfall_band{idx}.dat (int16 memmap)
- freqs0_band{idx}.npy (float64)
- rel_t_band{idx}.npy (int64)
- summary_band{idx}.npz (max/avg/min float32)
- tiers_band{idx}.json (multi-res frequency summaries)
- meta_band{idx}.json (metadata)

Implementation is delegated to `mancat_v2.py` which contains the full logic.
"""

from mancat_v2 import main


if __name__ == "__main__":
    main()


