#!/usr/bin/env python3
"""
mancat_v2_compute_band_stats.py — Precompute comprehensive band statistics from bronze data
and store in gold layer for fast retrieval.

Reads bronze band parquet files, computes min/max/avg, percentiles, occupancy metrics,
and threshold crossings per frequency bin, then writes to gold/survey/{site}/{YYYY-MM}/band{idx}_stats.parquet
"""
import argparse
import io
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

try:
    import duckdb
    import numpy as np
    import pyarrow as pa
    import pyarrow.parquet as pq
    import yaml
except ImportError as e:
    raise SystemExit(f"Missing required dependency: {e}. Install with: pip install duckdb numpy pyarrow pyyaml")

from minio import Minio


def load_config(path: Optional[str]) -> Dict:
    """Load YAML configuration file."""
    if not path:
        return {}
    cfg_path = Path(path).expanduser()
    if not cfg_path.exists():
        raise SystemExit(f"Config file not found: {cfg_path}")
    with cfg_path.open("r") as fh:
        return yaml.safe_load(fh) or {}


def build_minio_client(endpoint: str, access_key: str, secret_key: str, secure: bool) -> Minio:
    """Create MinIO client."""
    return Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)


def get_duckdb_connection(endpoint: str, access_key: str, secret_key: str, secure: bool, memory_limit: str = "55GB") -> duckdb.DuckDBPyConnection:
    """Create DuckDB connection configured for MinIO."""
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("SET s3_url_style='path';")
    con.execute("SET s3_endpoint=$1;", [endpoint])
    con.execute("SET s3_access_key_id=$1;", [access_key])
    con.execute("SET s3_secret_access_key=$1;", [secret_key])
    con.execute("SET s3_use_ssl=$1;", ["true" if secure else "false"])

    # Memory and performance optimizations to prevent OOM
    # Set memory limit (leaves ~9GB for OS on 64GB system)
    con.execute(f"SET memory_limit='{memory_limit}';")
    con.execute(f"SET max_memory='{memory_limit}';")  # Additional safeguard
    # Reduce threads to lower memory usage (8 threads for better memory efficiency)
    con.execute("SET threads=8;")
    # Disable insertion-order preservation to save memory
    con.execute("SET preserve_insertion_order=false;")
    # Disable object cache to reduce memory usage
    con.execute("SET enable_object_cache=false;")
    # Set temp directory for spillover if needed
    con.execute("SET temp_directory='/tmp';")
    return con


def parse_partitions(path_parts: List[str]) -> Dict[str, str]:
    """Parse partition keys from path parts."""
    parts = {}
    for part in path_parts:
        if "=" in part:
            k, v = part.split("=", 1)
            parts[k] = v
    return parts


def list_band_objects(
    client: Minio,
    bucket: str,
    site: str,
    year: str,
    month: str,
    mission_type: Optional[str],
    sensor: Optional[str],
    band_index: Optional[int],
    verbose: bool = True,
) -> List[Dict]:
    """List band parquet objects for the given filters."""
    scan_start = time.time()
    
    # Build optimized prefix with new path structure: bronze/mission_type={m}/site={s}/year={y}/month={m}/day={d}/sensor={s}/band={b}/
    if mission_type and site and year and month:
        if sensor:
            # Can't include sensor in prefix since it comes after day in new structure
            prefix = f"bronze/mission_type={mission_type}/site={site}/year={year}/month={month}/"
        else:
            prefix = f"bronze/mission_type={mission_type}/site={site}/year={year}/month={month}/"
    elif mission_type and site:
        prefix = f"bronze/mission_type={mission_type}/site={site}/"
    elif mission_type:
        prefix = f"bronze/mission_type={mission_type}/"
    else:
        prefix = "bronze/"
    
    band_re = re.compile(r"band(\d+)\.parquet$")
    bands: Dict[str, Dict] = {}  # Key: (band_index, mission_type, sensor)
    
    if verbose:
        print(f"  Scanning MinIO bucket '{bucket}' prefix '{prefix}'...")
        print(f"  Starting object enumeration...")
    
    # Pre-compute filter strings for faster early filtering
    year_filter = f"year={year}/"
    month_filter = f"month={month}/"
    
    object_count = 0
    matched_count = 0
    last_progress = time.time()
    first_object_time = None
    
    for obj in client.list_objects(bucket, prefix=prefix, recursive=True):
        if object_count == 0:
            first_object_time = time.time()
            if verbose:
                elapsed = time.time() - scan_start
                print(f"  ✓ MinIO connection working, first object received after {elapsed:.2f}s")
        
        object_count += 1
        
        # Show progress every 1000 objects, every 5 seconds, or on first 10 objects
        if verbose and (object_count <= 10 or object_count % 1000 == 0 or time.time() - last_progress > 5):
            elapsed = time.time() - scan_start
            rate = object_count / elapsed if elapsed > 0 else 0
            print(f"  ... scanned {object_count:,} objects ({matched_count:,} matched, {rate:.0f} obj/s)")
            last_progress = time.time()
        
        name = obj.object_name
        
        # Early filter: must contain year and month in path (faster than parsing)
        if year_filter not in name or month_filter not in name:
            continue
        
        # Early filter: must be parquet file
        if not name.endswith(".parquet"):
            continue
        
        # Early filter: must match band pattern
        fname = os.path.basename(name)
        m = band_re.match(fname)
        if not m:
            continue
        
        matched_count += 1
        
        # Now do full parsing only for files that passed early filters
        path_parts = name.split("/")
        parts = parse_partitions(path_parts)
        
        # Filter by site (year/month already checked above via string filter)
        if parts.get("site") != site:
            continue
        
        # Additional filters (only needed if not already in prefix)
        if not prefix.startswith(f"bronze/mission_type={mission_type}/") and mission_type and parts.get("mission_type") != mission_type:
            continue
        # sensor comes after day in new structure, so check separately
        if sensor and parts.get("sensor") != sensor:
            continue
        
        band_idx = int(m.group(1))
        if band_index is not None and band_idx != band_index:
            continue
        
        mt = parts.get("mission_type", "")
        sn = parts.get("sensor", "")
        key = f"{band_idx}|{mt}|{sn}"
        
        if key not in bands:
            bands[key] = {
                "band_index": band_idx,
                "band_label": parts.get("band", ""),
                "mission_type": mt,
                "sensor": sn,
                "object_keys": [],
                "days": set(),
                "run_ids": set(),
            }
        
        bands[key]["object_keys"].append(name)
        if parts.get("day"):
            bands[key]["days"].add(parts.get("day"))
        # run_id is no longer in path structure, so we can't extract it from path
        # It may be in metadata JSON, but we don't parse that here
    
    if verbose:
        elapsed = time.time() - scan_start
        rate = object_count / elapsed if elapsed > 0 else 0
        print(f"  ✓ Scanned {object_count:,} objects ({matched_count:,} matched) in {elapsed:.2f}s ({rate:.0f} obj/s)")
    
    return list(bands.values())


def power_dbm_to_array(batch: pa.RecordBatch, n_freqs: int) -> np.ndarray:
    """
    Efficiently convert Arrow list column (power_dbm) to 2D numpy array.
    
    Args:
        batch: Arrow RecordBatch containing power_dbm column
        n_freqs: Expected number of frequency bins per trace
        
    Returns:
        2D numpy array of shape (batch_size, n_freqs) as float32
    """
    power_col = batch.column("power_dbm")
    
    # Check if it's a FixedSizeListArray (fast path)
    if not pa.types.is_fixed_size_list(power_col.type):
        # Fallback for variable-length lists (slower)
        return np.stack([np.asarray(power_col[i].as_py(), dtype=np.float32) for i in range(batch.num_rows)], axis=0)
    
    # For FixedSizeListArray, .values is a flat array of length batch_rows * n_freqs
    # When using fetch_record_batch_reader, each batch is self-contained (no offset needed)
    flat = power_col.values.to_numpy(zero_copy_only=False)
    
    # If it's already float32, avoid astype copy
    if flat.dtype != np.float32:
        flat = flat.astype(np.float32, copy=False)
    
    return flat.reshape((batch.num_rows, n_freqs))


def compute_band_holds(
    con: duckdb.DuckDBPyConnection,
    bucket: str,
    band_info: Dict,
    config: Dict,
    batch_size: int = 256,
    verbose: bool = True,
) -> pa.Table:
    """
    Compute band holds (min/max/avg) using streaming batch processing.
    Skips UNNEST entirely by processing Arrow batches directly.
    
    Args:
        con: DuckDB connection (configured for MinIO)
        bucket: MinIO bucket name
        band_info: Band information dictionary
        config: Configuration dictionary
        batch_size: Number of traces to process per batch
        verbose: Whether to print progress
        
    Returns:
        PyArrow Table with holds statistics per frequency bin
    """
    start_time = time.time()
    
    paths = [f"s3://{bucket}/{key}" for key in band_info["object_keys"]]
    if verbose:
        print(f"    Reading {len(paths)} parquet file(s) from MinIO (holds-only mode)...")
    
    # Get metadata first (start_hz, step_hz, n_traces)
    # Get n_freqs separately by reading one row and checking array length
    meta_query = """
    SELECT
      MIN(start_hz) AS start_hz,
      MAX(stop_hz) AS stop_hz,
      MIN(step_hz) AS step_hz,
      COUNT(*) AS n_traces,
      MIN(unix_time_sec) AS unix_time_min,
      MAX(unix_time_sec) AS unix_time_max
    FROM read_parquet($1)
    """
    meta_start = time.time()
    meta_row = con.execute(meta_query, [paths]).fetchone()
    if verbose:
        print(f"    Metadata query completed in {time.time() - meta_start:.2f}s")
    
    start_hz, stop_hz, step_hz, n_traces, time_min, time_max = meta_row
    
    # Get n_freqs by reading one row and checking the array length
    # This is more reliable than calculating from step_hz (avoids rounding errors)
    n_freqs_query = "SELECT power_dbm FROM read_parquet($1) LIMIT 1"
    sample_row = con.execute(n_freqs_query, [paths]).fetchone()
    if sample_row and sample_row[0]:
        # sample_row[0] is the power_dbm array, get its length
        n_freqs = len(sample_row[0])
    else:
        # Fallback: calculate from step_hz (less reliable due to rounding)
        n_freqs = int(round((stop_hz - start_hz) / step_hz)) + 1
    if verbose:
        print(f"    Found {n_traces:,} traces")
        print(f"    Frequency range: {start_hz:.6e} - {stop_hz:.6e} Hz (step: {step_hz:.2f} Hz)")
        print(f"    Frequency bins: {n_freqs:,}")
        if time_min and time_max:
            dt_min = datetime.fromtimestamp(time_min)
            dt_max = datetime.fromtimestamp(time_max)
            print(f"    Time range: {dt_min.strftime('%Y-%m-%d %H:%M:%S')} to {dt_max.strftime('%Y-%m-%d %H:%M:%S')}")
    
    if verbose:
        print(f"    Computing holds (min/max/avg) using batch size {batch_size}...")
    
    # Initialize accumulators
    # Use float32 for min/max (matches power data precision)
    # Use float64 for sum (prevents precision drift over many traces)
    min_vec = np.full(n_freqs, np.inf, dtype=np.float32)
    max_vec = np.full(n_freqs, -np.inf, dtype=np.float32)
    sum_vec = np.zeros(n_freqs, dtype=np.float64)
    count_traces = 0
    
    # Stream Arrow batches from DuckDB using record batch reader (true streaming)
    stats_start = time.time()
    try:
        # Use fetch_record_batch() which returns a RecordBatchReader for true streaming
        # This avoids materializing the entire table upfront
        reader = con.execute(
            "SELECT power_dbm FROM read_parquet($1)", [paths]
        ).fetch_record_batch(batch_size)
        
        # Process batches as they stream
        total_batches = 0
        for batch in reader:
            batch_size_actual = batch.num_rows
            if batch_size_actual == 0:
                continue
            
            # Convert power_dbm list column to 2D numpy array
            power_array = power_dbm_to_array(batch, n_freqs)
            
            # Update accumulators (optimized to avoid unnecessary copies)
            min_vec = np.minimum(min_vec, power_array.min(axis=0))
            max_vec = np.maximum(max_vec, power_array.max(axis=0))
            # Use sum(..., dtype=float64) to accumulate directly into float64 without copying
            sum_vec += power_array.sum(axis=0, dtype=np.float64)
            count_traces += batch_size_actual
            
            total_batches += 1
            if verbose and total_batches % 10 == 0:
                elapsed = time.time() - stats_start
                print(f"      Processed {total_batches} batches ({count_traces:,} traces) in {elapsed:.2f}s")
        
    except Exception as e:
        if verbose:
            print(f"    Error during batch processing: {e}")
        raise
    
    if count_traces == 0:
        raise ValueError("No traces processed")
    
    # Compute mean
    mean_vec = (sum_vec / count_traces).astype(np.float32)
    
    if verbose:
        elapsed = time.time() - stats_start
        print(f"    Holds computation completed in {elapsed:.2f}s ({elapsed/60:.1f} minutes)")
        print(f"    Processed {count_traces:,} traces in {total_batches} batches")
    
    # Build result DataFrame
    import pandas as pd
    freq_indices = np.arange(1, n_freqs + 1, dtype=int)
    freq_hz = start_hz + (freq_indices - 1) * step_hz
    
    stats_df = pd.DataFrame({
        "freq_idx": freq_indices,
        "freq_hz": freq_hz,
        "power_min": min_vec,
        "power_mean": mean_vec,
        "power_max": max_vec,
    })
    
    # Add metadata columns (same value for all rows)
    stats_df["meta_site"] = band_info.get("site", "")
    stats_df["meta_year"] = band_info.get("year", "")
    stats_df["meta_month"] = band_info.get("month", "")
    stats_df["meta_band_index"] = band_info["band_index"]
    stats_df["meta_band_label"] = band_info.get("band_label") or ""
    stats_df["meta_mission_type"] = band_info["mission_type"]
    stats_df["meta_sensor"] = band_info["sensor"]
    stats_df["meta_total_traces"] = int(count_traces)
    stats_df["meta_time_min"] = int(time_min) if time_min else None
    stats_df["meta_time_max"] = int(time_max) if time_max else None
    stats_df["meta_freq_start_hz"] = float(start_hz)
    stats_df["meta_freq_stop_hz"] = float(stop_hz)
    stats_df["meta_freq_step_hz"] = float(step_hz)
    stats_df["meta_config_power_threshold"] = float(config.get("power_threshold", -100.0))
    stats_df["meta_days"] = ",".join(sorted(list(band_info["days"])))
    stats_df["meta_run_ids"] = ",".join(sorted(list(band_info["run_ids"])))
    
    # Convert to Arrow table
    try:
        table = pa.Table.from_pandas(stats_df)
    except Exception as e:
        if "numpy" in str(e).lower():
            raise SystemExit(f"numpy is required for pandas-to-arrow conversion. Install with: pip install numpy")
        raise
    
    if verbose:
        elapsed = time.time() - start_time
        print(f"    Total computation time: {elapsed:.2f}s ({elapsed/60:.1f} minutes)")
    
    return table


def compute_band_statistics(
    con: duckdb.DuckDBPyConnection,
    bucket: str,
    band_info: Dict,
    config: Dict,
    holds_only: bool = False,
    batch_size: int = 256,
    verbose: bool = True,
) -> pa.Table:
    """Compute comprehensive statistics for a band."""
    # If holds_only mode, use the fast streaming approach
    if holds_only:
        return compute_band_holds(con, bucket, band_info, config, batch_size=batch_size, verbose=verbose)
    
    # Otherwise, use the full UNNEST-based approach
    start_time = time.time()
    
    paths = [f"s3://{bucket}/{key}" for key in band_info["object_keys"]]
    if verbose:
        print(f"    Reading {len(paths)} parquet file(s) from MinIO...")
    
    # Get metadata (optimized: these are constant per file, so we can use DISTINCT or just first row)
    meta_query = """
    SELECT
      MIN(start_hz) AS start_hz,
      MAX(stop_hz) AS stop_hz,
      MIN(step_hz) AS step_hz,
      COUNT(*) AS n_traces,
      MIN(unix_time_sec) AS unix_time_min,
      MAX(unix_time_sec) AS unix_time_max
    FROM read_parquet($1)
    """
    meta_start = time.time()
    meta_row = con.execute(meta_query, [paths]).fetchone()
    if verbose:
        print(f"    Metadata query completed in {time.time() - meta_start:.2f}s")
    
    start_hz, stop_hz, step_hz, n_traces, time_min, time_max = meta_row
    if verbose:
        print(f"    Found {n_traces:,} traces")
        print(f"    Frequency range: {start_hz:.6e} - {stop_hz:.6e} Hz (step: {step_hz:.2f} Hz)")
        if time_min and time_max:
            dt_min = datetime.fromtimestamp(time_min)
            dt_max = datetime.fromtimestamp(time_max)
            print(f"    Time range: {dt_min.strftime('%Y-%m-%d %H:%M:%S')} to {dt_max.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Get thresholds from config
    power_threshold = config.get("power_threshold", -100.0)
    time_threshold = config.get("time_occupancy_threshold", -100.0)
    freq_threshold = config.get("frequency_occupancy_threshold", -100.0)
    percentiles = config.get("percentiles", [25, 50, 75, 95, 99])
    metrics = config.get("metrics", {})
    
    # Build statistics query
    select_parts = [
        "idx AS freq_idx",
        "MIN(val) AS power_min",
        "MAX(val) AS power_max",
        "AVG(val) AS power_mean",
    ]
    
    # Add percentiles if enabled (using APPROX_QUANTILE for better performance and lower memory)
    if metrics.get("percentiles", True):
        for p in percentiles:
            select_parts.append(f"APPROX_QUANTILE(val, {p/100.0}) AS power_p{p}")
    
    # Add occupancy metrics if enabled
    if metrics.get("time_occupancy", True):
        select_parts.append(
            f"CAST(SUM(CASE WHEN val > {time_threshold} THEN 1 ELSE 0 END) AS DOUBLE) / COUNT(*) * 100.0 AS time_occupancy_pct"
        )
    
    if metrics.get("frequency_occupancy", True):
        select_parts.append(
            f"CAST(SUM(CASE WHEN val > {freq_threshold} THEN 1 ELSE 0 END) AS DOUBLE) / COUNT(*) * 100.0 AS frequency_occupancy_pct"
        )
    
    if metrics.get("power_occupancy", True):
        select_parts.append(
            f"SUM(CASE WHEN val > {power_threshold} THEN 1 ELSE 0 END) AS power_occupancy_count"
        )
    
    # Add threshold crossings if enabled
    if metrics.get("threshold_crossings", True):
        # Count crossings: when value goes from below threshold to above, or vice versa
        # For simplicity, count how many values cross the threshold (not perfect but good approximation)
        select_parts.append(
            f"SUM(CASE WHEN val > {power_threshold} THEN 1 ELSE 0 END) AS threshold_crossings"
        )
    
    stats_query = f"""
    WITH src AS (
      SELECT power_dbm, unix_time_sec FROM read_parquet($1)
    ),
    unnested AS (
      SELECT 
        val,
        idx,
        unix_time_sec
      FROM src, UNNEST(power_dbm) WITH ORDINALITY AS t(val, idx)
    )
    SELECT
      {', '.join(select_parts)}
    FROM unnested
    GROUP BY idx
    ORDER BY idx
    """
    
    if verbose:
        print(f"    Computing statistics (min/max/avg", end="")
        if metrics.get("percentiles", True):
            print(f"/approx_percentiles", end="")
        if metrics.get("time_occupancy", True) or metrics.get("frequency_occupancy", True) or metrics.get("power_occupancy", True):
            print(f"/occupancy", end="")
        if metrics.get("threshold_crossings", True):
            print(f"/crossings", end="")
        print(f")...")
        print(f"    This may take several minutes for large datasets...")
        if n_traces > 10000:
            estimated_time_min = (n_traces / 10000) * 2  # Rough estimate: 2 min per 10k traces
            print(f"    Estimated processing time: ~{estimated_time_min:.1f} minutes")
    
    stats_start = time.time()
    last_progress_time = time.time()
    
    # Enable progress bar if available
    try:
        con.execute("SET enable_progress_bar=true;")
    except:
        pass
    
    # Execute query with progress monitoring
    try:
        stats_df = con.execute(stats_query, [paths]).fetchdf()
    except Exception as e:
        # Clear any intermediate results on error
        try:
            con.execute("RESET;")
        except:
            pass
        raise
    
    elapsed = time.time() - stats_start
    if verbose:
        print(f"    Statistics computation completed in {elapsed:.2f}s ({elapsed/60:.1f} minutes)")
    
    # Add frequency in Hz
    stats_df["freq_hz"] = start_hz + (stats_df["freq_idx"] - 1) * step_hz
    
    # Add metadata columns (same value for all rows)
    stats_df["meta_site"] = band_info.get("site", "")
    stats_df["meta_year"] = band_info.get("year", "")
    stats_df["meta_month"] = band_info.get("month", "")
    stats_df["meta_band_index"] = band_info["band_index"]
    stats_df["meta_band_label"] = band_info.get("band_label") or ""
    stats_df["meta_mission_type"] = band_info["mission_type"]
    stats_df["meta_sensor"] = band_info["sensor"]
    stats_df["meta_total_traces"] = int(n_traces)
    stats_df["meta_time_min"] = int(time_min) if time_min else None
    stats_df["meta_time_max"] = int(time_max) if time_max else None
    stats_df["meta_freq_start_hz"] = float(start_hz)
    stats_df["meta_freq_stop_hz"] = float(stop_hz)
    stats_df["meta_freq_step_hz"] = float(step_hz)
    stats_df["meta_config_power_threshold"] = float(power_threshold)
    # Store days and run_ids as comma-separated strings (easier for parquet)
    stats_df["meta_days"] = ",".join(sorted(list(band_info["days"])))
    stats_df["meta_run_ids"] = ",".join(sorted(list(band_info["run_ids"])))
    
    # Convert to Arrow table (requires numpy for pandas conversion)
    try:
        table = pa.Table.from_pandas(stats_df)
    except Exception as e:
        if "numpy" in str(e).lower():
            raise SystemExit(f"numpy is required for pandas-to-arrow conversion. Install with: pip install numpy")
        raise
    
    if verbose:
        elapsed = time.time() - start_time
        print(f"    Total computation time: {elapsed:.2f}s")
    
    return table


def write_band_stats_to_minio(
    client: Minio,
    bucket: str,
    site: str,
    year: str,
    month: str,
    band_index: int,
    table: pa.Table,
    holds_only: bool = False,
) -> str:
    """Write band statistics table to MinIO as parquet."""
    month_str = f"{year}-{month}"
    if holds_only:
        object_path = f"gold/survey/{site}/{month_str}/band{band_index}_holds.parquet"
    else:
        object_path = f"gold/survey/{site}/{month_str}/band{band_index}_stats.parquet"
    
    # Write table to bytes buffer
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    buffer.seek(0)
    
    # Upload to MinIO
    client.put_object(
        bucket,
        object_path,
        buffer,
        length=buffer.getbuffer().nbytes,
        content_type="application/octet-stream",
    )
    
    return object_path


def main():
    parser = argparse.ArgumentParser(
        description="Precompute band statistics from bronze data and store in gold layer"
    )
    parser.add_argument("--site", required=True, help="Site name")
    parser.add_argument("--year", required=True, help="Year (YYYY)")
    parser.add_argument("--month", required=True, help="Month (MM)")
    parser.add_argument("--endpoint", required=True, help="MinIO endpoint (host:port)")
    parser.add_argument("--access-key", required=True, help="MinIO access key")
    parser.add_argument("--secret-key", required=True, help="MinIO secret key")
    parser.add_argument("--bucket", default="rf-lake", help="MinIO bucket (default: rf-lake)")
    parser.add_argument("--secure", action="store_true", help="Use SSL/TLS for MinIO")
    parser.add_argument("--config", help="Path to config YAML file (default: band_stats_config.yaml)")
    parser.add_argument("--mission-type", default="survey", help="Filter by mission_type (default: survey)")
    parser.add_argument("--sensor", default="CRFS", help="Filter by sensor (default: CRFS)")
    parser.add_argument("--band-index", type=int, help="Process only specific band index (optional)")
    parser.add_argument("--memory-limit", default=None, help="DuckDB memory limit (e.g., '55GB'). Default: from config or '55GB'")
    parser.add_argument("--holds-only", action="store_true", help="Enable holds-only mode (skip UNNEST, compute only min/max/avg)")
    parser.add_argument("--holds-batch-size", type=int, default=None, help="Batch size for holds-only mode (number of traces per batch). Default: from config or 256")
    
    args = parser.parse_args()
    
    # Load configuration
    config_path = args.config or "band_stats_config.yaml"
    config = load_config(config_path)
    
    # Get memory limit from config or command line, default to 55GB
    memory_limit = args.memory_limit or config.get("duckdb_memory_limit", "55GB")
    
    # Get holds_only mode from command line or config
    holds_only = args.holds_only or config.get("holds_only", False)
    
    # Get batch size from command line or config, default to 256
    batch_size = args.holds_batch_size or config.get("holds_batch_traces", 256)
    
    # Build clients
    minio_client = build_minio_client(args.endpoint, args.access_key, args.secret_key, args.secure)
    duck_con = get_duckdb_connection(args.endpoint, args.access_key, args.secret_key, args.secure, memory_limit=memory_limit)
    
    # List bands
    print(f"\n{'='*80}")
    print(f"Precomputing Band Statistics")
    print(f"{'='*80}")
    print(f"Site: {args.site}")
    print(f"Year/Month: {args.year}-{args.month}")
    print(f"Bucket: {args.bucket}")
    if args.mission_type:
        print(f"Filter: mission_type={args.mission_type}")
    if args.sensor:
        print(f"Filter: sensor={args.sensor}")
    if args.band_index:
        print(f"Filter: band_index={args.band_index}")
    print(f"Config: {config_path}")
    print(f"{'='*80}\n")
    
    total_start = time.time()
    
    bands = list_band_objects(
        minio_client,
        args.bucket,
        args.site,
        args.year,
        args.month,
        args.mission_type,
        args.sensor,
        args.band_index,
        verbose=True,
    )
    
    if not bands:
        print(f"✗ No bands found for the specified filters.")
        return
    
    print(f"✓ Found {len(bands)} band(s) to process:\n")
    for i, band_info in enumerate(bands, 1):
        print(f"  [{i}] Band {band_info['band_index']} (mission_type={band_info['mission_type']}, sensor={band_info['sensor']}, "
              f"label={band_info.get('band_label', 'N/A')}, "
              f"objects={len(band_info['object_keys'])}, "
              f"days={len(band_info['days'])}, "
              f"runs={len(band_info['run_ids'])})")
    print()
    
    # Process each band
    for i, band_info in enumerate(bands, 1):
        band_idx = band_info["band_index"]
        mission_type = band_info["mission_type"]
        sensor = band_info["sensor"]
        num_objects = len(band_info["object_keys"])
        
        print(f"{'='*80}")
        print(f"[{i}/{len(bands)}] Processing band {band_idx}")
        print(f"  Mission: {mission_type} | Sensor: {sensor}")
        print(f"  Objects: {num_objects} parquet files")
        print(f"  Days: {sorted(band_info['days'])}")
        print(f"  Run IDs: {sorted(band_info['run_ids'])[:5]}{'...' if len(band_info['run_ids']) > 5 else ''}")
        print(f"  Config: power_threshold={config.get('power_threshold', -100.0)} dBm")
        print(f"{'='*80}")
        
        try:
            # Add site/year/month to band_info for metadata
            band_info["site"] = args.site
            band_info["year"] = args.year
            band_info["month"] = args.month
            
            mode_str = "holds (min/max/avg only)" if holds_only else "full statistics"
            print(f"  → Computing {mode_str} from {num_objects} parquet file(s)...")
            # Compute statistics
            stats_table = compute_band_statistics(
                duck_con, args.bucket, band_info, config, 
                holds_only=holds_only, batch_size=batch_size, verbose=True
            )
            
            print(f"  → Computed stats for {stats_table.num_rows} frequency bins")
            
            # Show some sample statistics
            if stats_table.num_rows > 0:
                # Convert to pandas to show sample
                import pandas as pd
                stats_df = stats_table.to_pandas()
                print(f"  → Frequency range: {stats_df['freq_hz'].min():.6e} - {stats_df['freq_hz'].max():.6e} Hz")
                print(f"  → Power range: {stats_df['power_min'].min():.2f} to {stats_df['power_max'].max():.2f} dBm")
                if 'time_occupancy_pct' in stats_df.columns:
                    avg_occupancy = stats_df['time_occupancy_pct'].mean()
                    print(f"  → Average time occupancy: {avg_occupancy:.2f}%")
            
            print(f"  → Uploading to MinIO...")
            # Write to MinIO
            object_path = write_band_stats_to_minio(
                minio_client,
                args.bucket,
                args.site,
                args.year,
                args.month,
                band_idx,
                stats_table,
                holds_only=holds_only,
            )
            
            # Get file size
            try:
                stat = minio_client.stat_object(args.bucket, object_path)
                size_mb = stat.size / (1024 * 1024)
                print(f"  ✓ Successfully wrote {stats_table.num_rows} frequency bins")
                print(f"  ✓ File: {object_path}")
                print(f"  ✓ Size: {size_mb:.2f} MB")
            except Exception:
                print(f"  ✓ Successfully wrote {stats_table.num_rows} frequency bins to {object_path}")
            
        except Exception as e:
            print(f"  ✗ ERROR processing band {band_idx}: {e}")
            import traceback
            traceback.print_exc()
        
        print()
    
    total_elapsed = time.time() - total_start
    print(f"{'='*80}")
    print(f"✓ Completed processing {len(bands)} band(s)")
    print(f"✓ Total execution time: {total_elapsed:.2f}s ({total_elapsed/60:.1f} minutes)")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()

