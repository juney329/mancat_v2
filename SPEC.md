# Goal
Build a Streamlit app to post-process recorded RF spectrum trace data:
- Show Max/Avg/Min traces (top) and a waterfall (bottom).
- Merge many .pbd2 files (files rotate at ~100MB).
- Zoom-aware waterfall: higher resolution as users zoom in.
- Peak finding with adjustable height/prominence/distance.
- Time playback of the data (simulate live stream).
- Easy markers & regions (persist to JSON).

# Data model
- Input: CRFS .pbd2 files (DataGeneric → TraceData → YDataStore DsDouble16).
- Output: Per-band artifacts:
  - waterfall_band{idx}.dat (int16 memmap, shape = [n_traces, n_freqs])
  - freqs0_band{idx}.npy (float64)
  - rel_t_band{idx}.npy (int64)
  - summary_band{idx}.npz (max/avg/min float32)
  - tiers_band{idx}.json (multi-res tier summaries)
  - meta_band{idx}.json ({db_min, db_max, scale, n_traces, n_freqs, f_start, f_stop, unix0, levels})
  - markers_band{idx}.json (created by UI; {"markers":[{freq_hz,label}], "regions":[{f0_hz,f1_hz,label}]})

# CLI (batch)
python mancat.py /path/to/captures   # merges & writes artifacts per band
python mancat.py /path/to/a /path/b  # multi-paths supported
python mancat.py /data --list-bands  # enumerate

# UI (viewer)
streamlit run streamlit_app.py
- Sidebar controls for vmin/vmax, peak params, playback window/speed.
- Top chart: Max/Avg/Min + detected peaks.
- Bottom chart: Heatmap Waterfall (zoom-aware).
- Markers: add single frequency+label.
- Regions: save current view or selection.
- Playback: sliding window over rel_t at chosen FPS.

# Technical constraints
- Use numpy, plotly, streamlit, scipy, grpcio-tools.
- Keep large arrays as memmaps to be responsive.
- Sort input traces by DataGeneric.UnixTime when merging.
- If grids differ slightly, re-interpolate onto the first trace’s freqs grid.
- Full-res waterfall is stored in .dat; tiers are summaries for zoomed-out views.
- Follow the file naming convention exactly.

# Files to create
- mancat.py           # batch processor (merge/index + tiers + summaries)
- streamlit_app.py    # interactive viewer
- requirements.txt    # streamlit, plotly, numpy, scipy, grpcio-tools
- pbd2.proto          # placeholder; explain where user should put actual schema

# Acceptance tests
- With synthetic data (or a tiny sample), running mancat.py produces:
  meta_band0.json, freqs0_band0.npy, rel_t_band0.npy, summary_band0.npz, tiers_band0.json, waterfall_band0.dat
- streamlit_app.py renders both charts; zooming narrows frequency span and increases detail.
- Peak sliders change detected points immediately.
- Play advances the time window.
- Markers/regions persist to markers_band0.json.
