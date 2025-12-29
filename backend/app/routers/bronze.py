import os
import re
from typing import Dict, List, Set

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder

from app.services.duck import get_connection
from app.services.minio_client import bucket_name, get_minio_client

router = APIRouter(prefix="/bronze", tags=["bronze"])


def _parse_partitions(path_parts: List[str]) -> Dict[str, str]:
    parts = {}
    for part in path_parts:
        if "=" in part:
            k, v = part.split("=", 1)
            parts[k] = v
    return parts


def _list_band_objects(
    mission_type: str,
    site: str,
    sensor: str,
    year: str,
    month: str,
    day: str | None,
    band_index_filter: int | None,
    band_label_filter: str | None,
    run_id_filter: str | None,
):
    client = get_minio_client()
    bucket = bucket_name()
    base_prefix = f"bronze/mission_type={mission_type}/site={site}/sensor={sensor}/"
    band_re = re.compile(r"band(\d+)\.parquet$")
    bands: Dict[int, Dict[str, object]] = {}

    for obj in client.list_objects(bucket, prefix=base_prefix, recursive=True):
        name = obj.object_name
        if not name.endswith(".parquet"):
            continue
        fname = os.path.basename(name)
        m = band_re.match(fname)
        if not m:
            continue
        band_idx = int(m.group(1))
        if band_index_filter is not None and band_idx != band_index_filter:
            continue
        parts = _parse_partitions(name.split("/"))
        if parts.get("year") != year or parts.get("month") != month:
            continue
        day_part = parts.get("day")
        if day is not None and day_part != day:
            continue
        run_id = parts.get("run_id")
        if run_id_filter is not None and run_id != run_id_filter:
            continue
        band_label = parts.get("band")
        if band_label_filter is not None and band_label != band_label_filter:
            continue

        entry = bands.setdefault(
            band_idx,
            {"band_index": band_idx, "band_label": band_label, "object_keys": [], "days": set(), "run_ids": set()},
        )
        entry["object_keys"].append(name)
        if band_label and entry.get("band_label") is None:
            entry["band_label"] = band_label
        if day_part:
            entry["days"].add(day_part)
        if run_id:
            entry["run_ids"].add(run_id)

    # Convert sets to sorted lists for JSON
    return [
        {
            "band_index": b["band_index"],
            "band_label": b.get("band_label"),
            "days": sorted(b["days"]),
            "run_ids": sorted(b["run_ids"]),
            "object_keys": sorted(b["object_keys"]),
        }
        for b in bands.values()
    ]


@router.get("/bands")
def list_bands(
    mission_type: str = Query(...),
    site: str = Query(...),
    sensor: str = Query(...),
    year: str = Query(...),
    month: str = Query(...),
    day: str | None = Query(None),
    band_index: int | None = Query(None),
    band_label: str | None = Query(None),
    run_id: str | None = Query(None),
):
    bands = _list_band_objects(
        mission_type=mission_type,
        site=site,
        sensor=sensor,
        year=year,
        month=month,
        day=day,
        band_index_filter=band_index,
        band_label_filter=band_label,
        run_id_filter=run_id,
    )
    return jsonable_encoder({"count": len(bands), "bands": sorted(bands, key=lambda b: b["band_index"])})


@router.get("/band/{band_index}/summary")
def band_summary(
    band_index: int,
    mission_type: str = Query(...),
    site: str = Query(...),
    sensor: str = Query(...),
    year: str = Query(...),
    month: str = Query(...),
    day: str | None = Query(None),
    run_id: str | None = Query(None),
    use_feature: bool = Query(True, description="Use feature.parquet if available; else scan bronze"),
    force_bronze: bool = Query(False, description="Force bronze scan, skip precomputed gold data"),
):
    # First, try precomputed gold stats (fastest path with per-frequency data)
    if not force_bronze:
        try:
            norm_month = f"{year}-{month}"
            stats_obj = f"s3://{bucket_name()}/gold/survey/{site}/{norm_month}/band{band_index}_stats.parquet"
            con = get_connection()
            
            # Check if file exists by attempting to read metadata
            try:
                stats_df = con.execute("SELECT * FROM read_parquet(?) LIMIT 1", [stats_obj]).fetchdf()
                
                if not stats_df.empty:
                    # Read full stats
                    full_stats_df = con.execute("SELECT * FROM read_parquet(?)", [stats_obj]).fetchdf()
                    
                    # Extract metadata from schema (stored in custom metadata)
                    # For now, we'll get basic info from the data
                    stats_list = []
                    for _, row in full_stats_df.iterrows():
                        stat_entry = {
                            "freq_hz": float(row.get("freq_hz", 0)),
                            "power_min": float(row.get("power_min", 0)),
                            "power_max": float(row.get("power_max", 0)),
                            "power_mean": float(row.get("power_mean", 0)),
                        }
                        # Add percentiles if present
                        for p in [25, 50, 75, 95, 99]:
                            col = f"power_p{p}"
                            if col in row:
                                stat_entry[col] = float(row[col]) if pd.notna(row[col]) else None
                        # Add occupancy metrics if present
                        if "time_occupancy_pct" in row:
                            stat_entry["time_occupancy_pct"] = float(row["time_occupancy_pct"]) if pd.notna(row["time_occupancy_pct"]) else None
                        if "frequency_occupancy_pct" in row:
                            stat_entry["frequency_occupancy_pct"] = float(row["frequency_occupancy_pct"]) if pd.notna(row["frequency_occupancy_pct"]) else None
                        if "power_occupancy_count" in row:
                            stat_entry["power_occupancy_count"] = int(row["power_occupancy_count"]) if pd.notna(row["power_occupancy_count"]) else None
                        if "threshold_crossings" in row:
                            stat_entry["threshold_crossings"] = int(row["threshold_crossings"]) if pd.notna(row["threshold_crossings"]) else None
                        stats_list.append(stat_entry)
                    
                    # Extract metadata from first row (metadata columns have meta_ prefix)
                    first_row = full_stats_df.iloc[0]
                    
                    meta_site = first_row.get("meta_site", "")
                    meta_band_label = first_row.get("meta_band_label", "")
                    meta_total_traces = first_row.get("meta_total_traces")
                    meta_time_min = first_row.get("meta_time_min")
                    meta_time_max = first_row.get("meta_time_max")
                    meta_freq_start = first_row.get("meta_freq_start_hz")
                    meta_freq_stop = first_row.get("meta_freq_stop_hz")
                    meta_freq_step = first_row.get("meta_freq_step_hz")
                    meta_days_str = first_row.get("meta_days", "")
                    meta_run_ids_str = first_row.get("meta_run_ids", "")
                    
                    # Parse comma-separated lists
                    days_list = [d.strip() for d in meta_days_str.split(",")] if meta_days_str else []
                    days_list = [d for d in days_list if d]  # Remove empty strings
                    run_ids_list = [r.strip() for r in meta_run_ids_str.split(",")] if meta_run_ids_str else []
                    run_ids_list = [r for r in run_ids_list if r]  # Remove empty strings
                    
                    return jsonable_encoder({
                        "band_index": band_index,
                        "band_label": meta_band_label if meta_band_label else None,
                        "n_traces": int(meta_total_traces) if meta_total_traces is not None else None,
                        "start_hz": float(meta_freq_start) if meta_freq_start is not None else None,
                        "stop_hz": float(meta_freq_stop) if meta_freq_stop is not None else None,
                        "step_hz": float(meta_freq_step) if meta_freq_step is not None else None,
                        "unix_time_min": int(meta_time_min) if meta_time_min is not None else None,
                        "unix_time_max": int(meta_time_max) if meta_time_max is not None else None,
                        "days": days_list,
                        "run_ids": run_ids_list,
                        "stats": stats_list,
                        "source": "precomputed_gold",
                    })
            except Exception:
                # File doesn't exist or can't be read, fall through
                pass
        except Exception:
            # Fall through to other methods if precomputed data unavailable
            pass
    
    # Try feature.parquet next if requested (band-level stats only)
    if use_feature:
        try:
            # Use site as location for feature path
            norm_month = f"{year}-{month}"
            feature_obj = f"s3://{bucket_name()}/gold/survey/{site}/{norm_month}/feature.parquet"
            con = get_connection()
            feature_df = con.execute(
                """
                SELECT 
                  band_index, band_label, start_hz, stop_hz, step_hz,
                  n_traces, n_freqs, unix_time_min, unix_time_max, days
                FROM read_parquet(?) 
                WHERE band_index = ?
                """,
                [feature_obj, band_index],
            ).fetchdf()
            
            if not feature_df.empty:
                row = feature_df.iloc[0]
                days_val = row["days"]
                if isinstance(days_val, list):
                    days_list = days_val
                elif hasattr(days_val, "tolist"):
                    days_list = days_val.tolist()
                else:
                    days_list = list(days_val) if days_val else []
                
                # Return summary from feature.parquet (no per-frequency stats)
                return jsonable_encoder({
                    "band_index": int(row["band_index"]),
                    "band_label": row["band_label"] if pd.notna(row["band_label"]) else None,
                    "n_traces": int(row["n_traces"]),
                    "start_hz": float(row["start_hz"]),
                    "stop_hz": float(row["stop_hz"]),
                    "step_hz": float(row["step_hz"]),
                    "unix_time_min": int(row["unix_time_min"]) if pd.notna(row["unix_time_min"]) else None,
                    "unix_time_max": int(row["unix_time_max"]) if pd.notna(row["unix_time_max"]) else None,
                    "days": days_list,
                    "stats": [],  # No per-frequency stats from feature.parquet
                    "source": "feature.parquet",
                })
        except Exception:
            # Fall through to bronze scan if feature.parquet fails
            pass
    
    # Fallback to bronze scan for full per-frequency stats
    bands = _list_band_objects(
        mission_type=mission_type,
        site=site,
        sensor=sensor,
        year=year,
        month=month,
        day=day,
        band_index_filter=band_index,
        band_label_filter=None,
        run_id_filter=run_id,
    )
    if not bands:
        raise HTTPException(status_code=404, detail="No matching band parquet objects found.")
    band = bands[0]
    paths = [f"s3://{bucket_name()}/{p}" for p in band["object_keys"]]

    try:
        con = get_connection()
        meta_row = con.execute(
            """
            SELECT
              MIN(start_hz) AS start_hz,
              MAX(stop_hz) AS stop_hz,
              MIN(step_hz) AS step_hz,
              COUNT(*) AS n_traces,
              MIN(unix_time_sec) AS unix_time_min,
              MAX(unix_time_sec) AS unix_time_max
            FROM read_parquet($1)
            """,
            [paths],
        ).fetchone()

        stats_rows = con.execute(
            """
            WITH src AS (
              SELECT power_dbm FROM read_parquet($1)
            )
            SELECT
              idx,
              MIN(val) AS power_min,
              MAX(val) AS power_max,
              AVG(val) AS power_mean
            FROM src, UNNEST(power_dbm) WITH ORDINALITY AS t(val, idx)
            GROUP BY idx
            ORDER BY idx
            """,
            [paths],
        ).fetchall()
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"DuckDB failed to read band parquet: {exc}")

    start_hz, stop_hz, step_hz, n_traces, unix_time_min, unix_time_max = meta_row
    band_stats = []
    for idx, pmin, pmax, pmean in stats_rows:
        freq_hz = float(start_hz + (idx - 1) * step_hz)
        band_stats.append(
            {"freq_hz": freq_hz, "power_min": float(pmin), "power_max": float(pmax), "power_mean": float(pmean)}
        )

    payload = {
        "band_index": band_index,
        "band_label": band.get("band_label"),
        "n_traces": int(n_traces),
        "start_hz": float(start_hz),
        "stop_hz": float(stop_hz),
        "step_hz": float(step_hz),
        "unix_time_min": int(unix_time_min) if unix_time_min is not None else None,
        "unix_time_max": int(unix_time_max) if unix_time_max is not None else None,
        "days": band.get("days", []),
        "stats": band_stats,
        "source": "bronze",
    }
    return jsonable_encoder(payload)


@router.get("/sites")
def list_sites():
    """List all unique sites from bronze data across all mission_types and sensors."""
    client = get_minio_client()
    bucket = bucket_name()
    prefix = "bronze/"
    sites = set()
    
    for obj in client.list_objects(bucket, prefix=prefix, recursive=True):
        path_parts = obj.object_name.split("/")
        parts = _parse_partitions(path_parts)
        site = parts.get("site")
        if site:
            sites.add(site)
    
    return jsonable_encoder({"sites": sorted(sites)})


@router.get("/months")
def list_months(site: str = Query(..., description="Site to list months for")):
    """List all unique months (YYYY-MM) for a given site from bronze data."""
    client = get_minio_client()
    bucket = bucket_name()
    prefix = f"bronze/"
    months = set()
    
    for obj in client.list_objects(bucket, prefix=prefix, recursive=True):
        path_parts = obj.object_name.split("/")
        parts = _parse_partitions(path_parts)
        if parts.get("site") != site:
            continue
        year = parts.get("year")
        month = parts.get("month")
        if year and month:
            # Validate year is 4 digits and month is 2 digits
            if len(year) == 4 and year.isdigit() and len(month) == 2 and month.isdigit():
                months.add(f"{year}-{month}")
    
    return jsonable_encoder({"site": site, "months": sorted(months)})


@router.get("/bands-by-site-month")
def list_bands_by_site_month(
    site: str = Query(..., description="Site"),
    year: str = Query(..., description="Year (YYYY)"),
    month: str = Query(..., description="Month (MM)"),
):
    """List all bands available for a site/year/month across all mission_types and sensors."""
    client = get_minio_client()
    bucket = bucket_name()
    prefix = f"bronze/"
    band_re = re.compile(r"band(\d+)\.parquet$")
    bands: Dict[str, Dict[str, object]] = {}  # Key: (band_index, mission_type, sensor)
    
    for obj in client.list_objects(bucket, prefix=prefix, recursive=True):
        name = obj.object_name
        if not name.endswith(".parquet"):
            continue
        fname = os.path.basename(name)
        m = band_re.match(fname)
        if not m:
            continue
        
        path_parts = name.split("/")
        parts = _parse_partitions(path_parts)
        
        if parts.get("site") != site or parts.get("year") != year or parts.get("month") != month:
            continue
        
        band_idx = int(m.group(1))
        mission_type = parts.get("mission_type", "")
        sensor = parts.get("sensor", "")
        band_label = parts.get("band", "")
        day_part = parts.get("day", "")
        run_id = parts.get("run_id", "")
        
        # Create a unique key per band_index, mission_type, sensor combination
        key = f"{band_idx}|{mission_type}|{sensor}"
        
        if key not in bands:
            bands[key] = {
                "band_index": band_idx,
                "band_label": band_label,
                "mission_type": mission_type,
                "sensor": sensor,
                "year": year,
                "month": month,
                "days": set(),
                "run_ids": set(),
            }
        
        if day_part:
            bands[key]["days"].add(day_part)
        if run_id:
            bands[key]["run_ids"].add(run_id)
    
    # Convert sets to sorted lists and sort by band_index
    result = []
    for b in bands.values():
        result.append({
            "band_index": b["band_index"],
            "band_label": b.get("band_label"),
            "mission_type": b["mission_type"],
            "sensor": b["sensor"],
            "year": b["year"],
            "month": b["month"],
            "days": sorted(b["days"]),
            "run_ids": sorted(b["run_ids"]),
        })
    
    result.sort(key=lambda x: (x["band_index"], x["mission_type"], x["sensor"]))
    return jsonable_encoder({"site": site, "year": year, "month": month, "count": len(result), "bands": result})

