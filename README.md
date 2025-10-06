# mancat_v2

Post-process recorded RF spectrum trace data into per-band artifacts and view them with a Streamlit app.

## Features
- Merge CRFS `.pbd2` chunks and build per-band artifacts
- Max/Avg/Min traces and zoom-aware waterfall
- Peak detection with adjustable params
- Time playback (sliding window)
- Markers and regions persisted to JSON

## Quick start
1. Create a virtualenv and install deps:
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

2. Generate protobufs (if you have the real schema):
```bash
# Replace pbd2.proto with the actual CRFS schema when available
python -m grpc_tools.protoc -I. --python_out=. pbd2.proto
```

3. Build artifacts from .pbd2 chunks:
```bash
python mancat.py /path/to/captures
# Optional: list bands
python mancat.py /path/to/captures --list-bands
```

4. Launch the viewer:
```bash
streamlit run streamlit_app.py
```

## Artifacts per band
- `waterfall_band{idx}.dat` — int16 memmap `[n_traces, n_freqs]`
- `freqs0_band{idx}.npy` — float64 frequency axis
- `rel_t_band{idx}.npy` — int64 relative seconds
- `summary_band{idx}.npz` — float32 `max/avg/min` over time
- `tiers_band{idx}.json` — multi-resolution frequency summaries
- `meta_band{idx}.json` — metadata `{db_min, db_max, scale, n_traces, n_freqs, f_start, f_stop, unix0, levels}`
- `markers_band{idx}.json` — UI-created markers and regions

## Notes
- Large arrays are memory-mapped for responsiveness
- Slight grid differences are re-interpolated onto the first trace’s grid
- Zoom-aware: viewer chooses tier resolution by span; use the sidebar frequency span to keep traces and waterfall aligned

## Requirements
See `requirements.txt`. Tested on Python 3.12.

## License
MIT
