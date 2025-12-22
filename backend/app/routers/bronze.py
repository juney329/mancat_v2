import os
import re
from typing import Dict, List, Set

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
):
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
        "run_ids": band.get("run_ids", []),
        "days": band.get("days", []),
        "stats": band_stats,
    }
    return jsonable_encoder(payload)

