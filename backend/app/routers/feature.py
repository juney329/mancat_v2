from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder

from app.services.duck import bucket_name, get_connection
from app.services.minio_client import bucket_name as get_bucket_name, get_minio_client

router = APIRouter(prefix="/feature", tags=["feature"])


def _normalize_month(month: str) -> str:
    m = month.replace("/", "-").replace(".", "-").strip()
    if len(m) == 6 and m.isdigit():
        return f"{m[:4]}-{m[4:]}"
    if len(m) == 7 and m[4] == "-":
        return m
    raise HTTPException(status_code=400, detail="month must be YYYY-MM or YYYYMM")


def _feature_path(location: str, month: str) -> str:
    return f"s3://{bucket_name()}/gold/survey/{location}/{month}/feature.parquet"


@router.get("")
def get_feature(
    location: str = Query(..., description="Location (path segment after gold/survey/)"),
    month: str = Query(..., description="Month in YYYY-MM or YYYYMM"),
    band_index: int | None = Query(None),
    band_label: str | None = Query(None),
    day: str | None = Query(None, description="Filter rows whose days array contains this DD"),
    run_id: str | None = Query(None, description="Filter rows whose run_ids array contains this value"),
    limit: int = Query(500, ge=1, le=5000),
):
    norm_month = _normalize_month(month)
    obj = _feature_path(location, norm_month)
    try:
        con = get_connection()
        sql = "SELECT * FROM read_parquet(?) WHERE 1=1"
        params: list[object] = [obj]
        if band_index is not None:
            sql += " AND band_index = ?"
            params.append(band_index)
        if band_label is not None:
            sql += " AND band_label = ?"
            params.append(band_label)
        if day is not None:
            sql += " AND list_contains(days, ?)"
            params.append(day)
        if run_id is not None:
            sql += " AND list_contains(run_ids, ?)"
            params.append(run_id)
        sql += " ORDER BY band_index LIMIT ?"
        params.append(limit)
        rows = con.execute(sql, params).fetch_arrow_table().to_pylist()
    except Exception as exc:  # pragma: no cover - runtime dependency
        raise HTTPException(status_code=404, detail=f"Unable to read feature parquet: {exc}")
    return jsonable_encoder(rows)


@router.get("/schema")
def get_feature_schema(
    location: str = Query(..., description="Location (path segment after gold/survey/)"),
    month: str = Query(..., description="Month in YYYY-MM or YYYYMM"),
):
    norm_month = _normalize_month(month)
    obj = _feature_path(location, norm_month)
    try:
        con = get_connection()
        schema_rows = con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [obj]).fetchall()
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=404, detail=f"Unable to read feature schema: {exc}")
    schema = [
        {"column": name, "type": dtype, "null": null, "key": key, "default": default, "extra": extra}
        for name, dtype, null, key, default, extra in schema_rows
    ]
    return {"path": obj, "schema": schema}


@router.get("/locations")
def list_locations():
    """List all available locations from gold/survey/."""
    client = get_minio_client()
    bucket = get_bucket_name()
    prefix = "gold/survey/"
    locations = set()
    
    for obj in client.list_objects(bucket, prefix=prefix, recursive=False):
        # Extract location from path like "gold/survey/LOCATION/"
        parts = obj.object_name.replace(prefix, "").split("/")
        if parts and parts[0]:
            locations.add(parts[0])
    
    return jsonable_encoder({"locations": sorted(locations)})


@router.get("/months")
def list_months(location: str = Query(..., description="Location to list months for")):
    """List all available months (YYYY-MM) for a given location."""
    client = get_minio_client()
    bucket = get_bucket_name()
    prefix = f"gold/survey/{location}/"
    months = set()
    
    for obj in client.list_objects(bucket, prefix=prefix, recursive=False):
        # Extract month from path like "gold/survey/LOCATION/YYYY-MM/"
        parts = obj.object_name.replace(prefix, "").split("/")
        if parts and parts[0] and parts[0].endswith("/"):
            month = parts[0].rstrip("/")
            # Validate it looks like YYYY-MM
            if len(month) == 7 and month[4] == "-":
                months.add(month)
    
    return jsonable_encoder({"location": location, "months": sorted(months)})

