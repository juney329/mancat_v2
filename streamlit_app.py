# streamlit_app.py — Interactive viewer for artifacts produced by mancat_v2.py
import os, json, time, math, glob
import numpy as np
import streamlit as st
import plotly.graph_objects as go
from scipy.signal import find_peaks

st.set_page_config(layout="wide", page_title="RF Spectrum Post-Processor")

# ---------- Loaders ----------
@st.cache_data
def load_meta(band_idx):
    with open(f"meta_band{band_idx}.json","r") as f: meta = json.load(f)
    freqs = np.load(f"freqs0_band{band_idx}.npy")
    rel_t = np.load(f"rel_t_band{band_idx}.npy")
    return meta, freqs, rel_t

def open_memmap(band_idx, shape):
    return np.memmap(f"waterfall_band{band_idx}.dat", dtype=np.int16, mode="r", shape=shape)

@st.cache_data
def load_summary(band_idx):
    d = np.load(f"summary_band{band_idx}.npz")
    return d["max"], d["avg"], d["min"]

@st.cache_data
def load_tiers(band_idx):
    with open(f"tiers_band{band_idx}.json","r") as f: tiers = json.load(f)
    return tiers

def load_markers(band_idx):
    fn = f"markers_band{band_idx}.json"
    if not os.path.exists(fn):
        return {"markers": [], "regions": []}
    with open(fn,"r") as f: return json.load(f)

def save_markers(band_idx, data):
    with open(f"markers_band{band_idx}.json","w") as f: json.dump(data, f, indent=2)

# ---------- Helpers ----------
def choose_tier(tiers, f0, f1, max_points=2200):
    best = None
    for t in tiers:
        f = np.asarray(t["f_axis"])
        m = (f>=f0) & (f<=f1)
        pts = int(m.sum())
        if pts == 0: 
            continue
        if pts <= max_points:
            if best is None or pts > best[0]:
                best = (pts, t, m)
    return (None, None, None) if best is None else best

def slice_full(meta, freqs, t0_idx, t1_idx, f0, f1, max_freq_points=1800):
    sf = int(np.searchsorted(freqs, f0, side="left"))
    ef = int(np.searchsorted(freqs, f1, side="right"))
    sf = max(0, min(sf, len(freqs)-1))
    ef = max(sf+1, min(ef, len(freqs)))
    f_slice = freqs[sf:ef]
    dec = max(1, int(math.ceil(len(f_slice)/max_freq_points)))
    idx = slice(sf, ef, dec)
    mem = open_memmap(band, (meta["n_traces"], meta["n_freqs"]))[t0_idx:t1_idx, idx]
    wf_f = (mem.astype(np.float32)/meta["scale"]) + meta["db_min"]
    return freqs[idx], wf_f

# ---------- UI ----------
st.title("RF Spectrum Post-Processor")

meta_files = sorted(glob.glob("meta_band*.json"))
bands = [int(f.split("meta_band")[1].split(".json")[0]) for f in meta_files]
if not bands:
    st.error("No meta_band*.json found. Run mancat_v2.py first.")
    st.stop()

with st.sidebar:
    band = st.selectbox("Band", bands)
    meta, freqs, rel_t = load_meta(band)
    db_min, db_max, scale = meta["db_min"], meta["db_max"], meta["scale"]
    nT, nF = meta["n_traces"], meta["n_freqs"]

    st.subheader("Waterfall scale (dBm)")
    vmin = st.slider("vmin", db_min, db_max, max(db_min, -120.0), 1.0)
    vmax = st.slider("vmax", db_min, db_max, min(db_max, -80.0), 1.0)

    st.subheader("Peaks")
    pk_curve = st.radio("Curve", ["Avg","Max"], horizontal=True)
    pk_height = st.slider("Min height", db_min, db_max, -90.0, 1.0)
    pk_prom   = st.slider("Prominence", 0.0, 40.0, 6.0, 0.5)
    pk_dist   = st.slider("Min distance (points)", 1, 1000, 25)

    st.subheader("Playback")
    window_s  = st.slider("Window (seconds)", 1, max(2, int(rel_t.max() or 1)), 5)
    speed_fps = st.slider("Speed (frames/sec)", 1, 20, 5)
    st.subheader("Top chart behavior")
    follow_window = st.checkbox("Use current time window", value=True, help="When enabled, Max/Avg/Min are computed from the visible time window. When disabled, precomputed tiers over all time are used.")

# session state
if "playing" not in st.session_state: st.session_state.playing = False
if "t0" not in st.session_state:      st.session_state.t0 = 0
if "view_f0" not in st.session_state: st.session_state.view_f0 = float(freqs[0])
if "view_f1" not in st.session_state: st.session_state.view_f1 = float(freqs[-1])

# Controls row
c1,c2,c3,c4 = st.columns([1,1,1,2])
with c1:
    if st.button("⏵ Play" if not st.session_state.playing else "⏸ Pause"):
        st.session_state.playing = not st.session_state.playing
with c2:
    if st.button("⟲ Reset view"):
        st.session_state.view_f0 = float(freqs[0])
        st.session_state.view_f1 = float(freqs[-1])
with c3:
    t_pos = st.slider("Time index", 0, meta["n_traces"]-1, st.session_state.t0)
    st.session_state.t0 = t_pos

# time window
def time_window_indices(t0_idx, secs):
    t0_val = rel_t[min(t0_idx, len(rel_t)-1)]
    t1_val = t0_val + secs
    t1_idx = int(np.searchsorted(rel_t, t1_val, side="right"))
    t1_idx = min(max(t1_idx, t0_idx+1), len(rel_t))
    return t0_idx, t1_idx

t0_idx, t1_idx = time_window_indices(st.session_state.t0, window_s)

# frequency window
f0 = st.session_state.view_f0
f1 = st.session_state.view_f1

# summaries
s_max, s_avg, s_min = load_summary(band)

# choose tier for top chart and build figure
tiers = load_tiers(band)
pts, tier, mask = choose_tier(tiers, f0, f1, max_points=2200)

# build top figure
top = go.Figure()
if follow_window:
    f_slice, wf_win = slice_full(meta, freqs, t0_idx, t1_idx, f0, f1)
    top.add_trace(go.Scatter(x=f_slice/1e6, y=wf_win.max(axis=0), name="Max"))
    top.add_trace(go.Scatter(x=f_slice/1e6, y=wf_win.mean(axis=0), name="Avg"))
    top.add_trace(go.Scatter(x=f_slice/1e6, y=wf_win.min(axis=0), name="Min"))
    curve_y = wf_win.mean(axis=0) if pk_curve=="Avg" else wf_win.max(axis=0)
    curve_x = f_slice
else:
    if tier is not None:
        f_axis = np.asarray(tier["f_axis"])[mask]
        top.add_trace(go.Scatter(x=f_axis/1e6, y=np.asarray(tier["max"])[mask], name="Max"))
        top.add_trace(go.Scatter(x=f_axis/1e6, y=np.asarray(tier["avg"])[mask], name="Avg"))
        top.add_trace(go.Scatter(x=f_axis/1e6, y=np.asarray(tier["min"])[mask], name="Min"))
        curve_y = np.asarray(tier["avg"])[mask] if pk_curve=="Avg" else np.asarray(tier["max"])[mask]
        curve_x = f_axis
    else:
        f_slice, wf_win = slice_full(meta, freqs, t0_idx, t1_idx, f0, f1)
        top.add_trace(go.Scatter(x=f_slice/1e6, y=wf_win.max(axis=0), name="Max"))
        top.add_trace(go.Scatter(x=f_slice/1e6, y=wf_win.mean(axis=0), name="Avg"))
        top.add_trace(go.Scatter(x=f_slice/1e6, y=wf_win.min(axis=0), name="Min"))
        curve_y = wf_win.mean(axis=0) if pk_curve=="Avg" else wf_win.max(axis=0)
        curve_x = f_slice

# peak finding
peaks, props = find_peaks(curve_y, height=pk_height, prominence=pk_prom, distance=pk_dist)
top.add_trace(go.Scatter(x=curve_x[peaks]/1e6, y=curve_y[peaks], mode="markers", name="Peaks", marker=dict(size=8, symbol="x")))
top.update_layout(title=f"Band {band} — Traces & Peaks", xaxis_title="Frequency (MHz)", yaxis_title="dBm", height=380)

top_ev = st.plotly_chart(top)

# waterfall
wf_faxis, wf_block = slice_full(meta, freqs, t0_idx, t1_idx, f0, f1, max_freq_points=1600)
wf_fig = go.Figure(data=go.Heatmap(
    x=wf_faxis/1e6, y=rel_t[t0_idx:t1_idx], z=wf_block,
    zmin=vmin, zmax=vmax, colorscale="Inferno", colorbar=dict(title="dBm")
))
wf_fig.update_layout(title="Waterfall", xaxis_title="Frequency (MHz)", yaxis_title="Time (s)", height=520)
st.plotly_chart(wf_fig)

# markers & regions
mrk = load_markers(band)
with st.expander("Markers & Regions"):
    mcols = st.columns([1,1,1,2])
    with mcols[0]:
        m_freq = st.number_input("Marker freq (MHz)", value=float((f0+f1)/2/1e6))
    with mcols[1]:
        m_label = st.text_input("Label", value="Marker")
    with mcols[2]:
        if st.button("➕ Add marker"):
            mrk["markers"].append({"freq_hz": m_freq*1e6, "label": m_label})
            save_markers(band, mrk)
            st.success("Marker added.")
    st.write("Regions use current view. Adjust zoom/pan on the top chart, then click save.")
    r_label = st.text_input("Region label", value="Region of Interest")
    if st.button("➕ Save region from current view"):
        mrk["regions"].append({"f0_hz": float(f0), "f1_hz": float(f1), "label": r_label})
        save_markers(band, mrk)
        st.success("Region saved.")
    # Show table of peaks
    if len(peaks):
        st.write("Detected peaks (current curve):")
        import pandas as pd
        df = pd.DataFrame({"freq_MHz": curve_x[peaks]/1e6, "level_dBm": curve_y[peaks]})
        st.dataframe(df, width='stretch')
    st.json(mrk)

# playback loop
if st.session_state.playing:
    st.session_state.t0 = min(st.session_state.t0 + 1, meta["n_traces"]-2)
    time.sleep(1.0/float(max(speed_fps,1)))
    st.rerun()
