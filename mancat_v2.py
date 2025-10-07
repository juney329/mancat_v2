#!/usr/bin/env python3
# mancat_v2.py — Merge CRFS .pbd2, write per-band artifacts (memmap waterfall, summaries, tiers).
# Assumes pbd2_pb2.py already exists beside this file.
import os, math, json, struct, argparse, glob
import numpy as np

# ---------- I/O helpers ----------
def find_all_pbd2(inputs):
    files = []
    for p in inputs:
        if os.path.isdir(p):
            for root, _, fnames in os.walk(p):
                for f in fnames:
                    if f.lower().endswith(".pbd2"):
                        files.append(os.path.join(root, f))
        elif os.path.isfile(p) and p.lower().endswith(".pbd2"):
            files.append(p)
    return sorted(files)

def read_len_delimited_msgs(path):
    with open(path, "rb") as f:
        while True:
            hdr = f.read(4)
            if len(hdr) < 4:
                return
            ln = int.from_bytes(hdr, byteorder="little", signed=False)
            buf = f.read(ln)
            if len(buf) < ln:
                return
            yield buf

def decode_trace_el(el):
    # DataGeneric.Data.Elements[i].TraceData.YDataStore.DsDouble16 (CRFS style)
    ds = el.TraceData.YDataStore.DsDouble16
    # uint16 codes over [Min,Max] range
    codes = np.frombuffer(ds.Bytes, dtype=np.uint16)
    power = ds.Min + (codes.astype(np.float64)/65535.0) * (ds.Max - ds.Min)
    freqs = np.linspace(el.IndexStart, el.IndexStop, num=len(codes), dtype=np.float64)
    return freqs, power

def discover_bands(files):
    import pbd2_pb2
    bands = set()
    for fp in files:
        for raw in read_len_delimited_msgs(fp):
            dg = pbd2_pb2.DataGeneric(); dg.ParseFromString(raw)
            for el in dg.Data.Elements:
                if hasattr(el, "TraceData") and el.IndexStart < el.IndexStop:
                    bands.add((float(el.IndexStart), float(el.IndexStop)))
    return sorted(bands, key=lambda x: (x[0], x[1]))

# ---------- Per-band processing ----------
def process_band(idx, f_start, f_stop, files, db_min=-200.0, db_max=0.0, scale=100):
    import pbd2_pb2

    freqs0 = None
    times  = []
    rows   = []

    # Collect all traces in this band across all files
    for fp in files:
        for raw in read_len_delimited_msgs(fp):
            dg = pbd2_pb2.DataGeneric(); dg.ParseFromString(raw)
            t = int(dg.UnixTime)
            for el in dg.Data.Elements:
                if not hasattr(el, "TraceData"): 
                    continue
                if (float(el.IndexStart), float(el.IndexStop)) != (f_start, f_stop):
                    continue
                f, p = decode_trace_el(el)
                if freqs0 is None:
                    freqs0 = f
                else:
                    # Re-grid if needed (rare)
                    if len(f) != len(freqs0) or f[0] != freqs0[0] or f[-1] != freqs0[-1]:
                        p = np.interp(freqs0, f, p)
                rows.append(p.astype(np.float32))
                times.append(t)

    if not rows:
        print(f"[band {idx}] No traces found.")
        return

    # Sort by time
    order = np.argsort(times)
    times = np.array(times, dtype=np.int64)[order]
    wf    = np.vstack(rows)[order, :]  # shape (T, F), float32

    nT, nF = wf.shape

    # Quantize to int16 in [db_min, db_max] for compact memmap
    wf_q = np.round((np.clip(wf, db_min, db_max) - db_min) * scale).astype(np.int16)

    # Write memmap
    wf_path = f"waterfall_band{idx}.dat"
    mmap = np.memmap(wf_path, dtype=np.int16, mode="w+", shape=(nT, nF))
    mmap[:] = wf_q[:]
    del mmap  # flush

    # Axes and meta (write both legacy *_band{idx} and backend-style _{idx} file names)
    freqs0_out = freqs0.astype(np.float64)
    np.save(f"freqs0_band{idx}.npy", freqs0_out)
    np.save(f"freqs0_{idx}.npy", freqs0_out)

    rel_t = (times - times[0]).astype(np.int64)
    np.save(f"rel_t_band{idx}.npy", rel_t)
    np.save(f"rel_t_{idx}.npy", rel_t)

    meta = {
        "db_min": float(db_min),
        "db_max": float(db_max),
        "scale":  int(scale),
        "n_traces": int(nT),
        "n_freqs":  int(nF),
        "f_start": float(f_start),
        "f_stop":  float(f_stop),
        "unix0":   int(times[0]),
        "levels":  []  # filled below
    }

    # Full-res summaries (write both naming schemes)
    wf_f = (wf_q.astype(np.float32)/scale) + db_min
    s_max = wf_f.max(axis=0).astype(np.float32)
    s_avg = wf_f.mean(axis=0).astype(np.float32)
    s_min = wf_f.min(axis=0).astype(np.float32)
    np.savez(f"summary_band{idx}.npz", max=s_max, avg=s_avg, min=s_min)
    np.savez(f"summary_{idx}.npz", max=s_max, avg=s_avg, min=s_min)

    # Multi-resolution frequency tiers (min/avg/max per decimation bin)
    tiers = []
    for dec in (1, 2, 4, 8):
        k = (nF + dec - 1)//dec
        # streaming reduction over time to keep memory low
        acc_min = np.full(k,  np.inf,  dtype=np.float32)
        acc_max = np.full(k, -np.inf,  dtype=np.float32)
        acc_sum = np.zeros(k, dtype=np.float64)
        acc_cnt = 0

        # read back in blocks (memory-map)
        block = 1024
        r_mmap = np.memmap(wf_path, dtype=np.int16, mode="r", shape=(nT, nF))
        for s in range(0, nT, block):
            e = min(s+block, nT)
            blk = (r_mmap[s:e].astype(np.float32)/scale) + db_min  # (B, nF)
            pad = k*dec - nF
            if pad > 0:
                blk = np.pad(blk, ((0,0),(0,pad)), constant_values=np.nan)
            resh = blk.reshape(e-s, k, dec)
            bmin = np.nanmin(resh, axis=2).min(axis=0)  # (k,)
            bmax = np.nanmax(resh, axis=2).max(axis=0)  # (k,)
            bavg = np.nanmean(resh, axis=(0,2))         # (k,)
            acc_min = np.minimum(acc_min, bmin)
            acc_max = np.maximum(acc_max, bmax)
            acc_sum += bavg
            acc_cnt += 1
        del r_mmap

        tiers.append({
            "decim": dec,
            "min": acc_min.tolist(),
            "max": acc_max.tolist(),
            "avg": (acc_sum/max(acc_cnt,1)).astype(np.float32).tolist(),
            "f_axis": freqs0[::dec][:k].astype(np.float64).tolist()
        })
        meta["levels"].append({"decim": dec, "k": int(k)})

    with open(f"meta_band{idx}.json", "w") as f:
        json.dump(meta, f, indent=2)
    with open(f"meta_{idx}.json", "w") as f:
        json.dump(meta, f, indent=2)
    with open(f"tiers_band{idx}.json","w") as f:
        json.dump(tiers, f)

    print(f"[band {idx}] wrote: waterfall_band{idx}.dat, freqs0/rel_t, summary, meta, tiers")


def main():
    ap = argparse.ArgumentParser(description="Merge CRFS .pbd2 files and build per-band datasets.")
    ap.add_argument("inputs", nargs="+", help="Files and/or directories containing .pbd2 chunks")
    ap.add_argument("--list-bands", action="store_true", help="List discovered bands only")
    ap.add_argument("--db-min", type=float, default=-200.0)
    ap.add_argument("--db-max", type=float, default=0.0)
    ap.add_argument("--scale",  type=int,   default=100, help="quantization scale (int16 codes per dB)")
    args = ap.parse_args()

    files = find_all_pbd2(args.inputs)
    if not files:
        print("No .pbd2 files found."); return

    bands = discover_bands(files)
    if not bands:
        print("No bands discovered."); return

    if args.list_bands:
        print("Bands:")
        for i, (s,e) in enumerate(bands):
            print(f"  [{i}] {s/1e6:.3f}-{e/1e6:.3f} MHz")
        return

    for i, (s,e) in enumerate(bands):
        process_band(i, s, e, files, db_min=args.db_min, db_max=args.db_max, scale=args.scale)


if __name__ == "__main__":
    main()
