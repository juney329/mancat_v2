from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder

from app.services.duck import bucket_name, get_connection

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
        rows = con.execute(sql, params).fetchdf().to_dict(orient="records")
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

