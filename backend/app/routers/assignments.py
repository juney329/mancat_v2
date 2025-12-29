import io

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Body
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

from app.services.minio_client import bucket_name, get_minio_client

router = APIRouter(prefix="/assignments", tags=["assignments"])


def _assignments_path(location: str, month: str) -> str:
    return f"gold/survey/{location}/{month}/assignments.csv"


class AssignmentCreate(BaseModel):
    lat: float
    long: float
    center_freq_hz: float
    bandwidth_hz: float
    label: str


class AssignmentDelete(BaseModel):
    center_freq_hz: float
    bandwidth_hz: float


@router.post("/upload")
async def upload_assignments(
    location: str = Query(..., description="Location"),
    month: str = Query(..., description="Month in YYYY-MM format"),
    file: UploadFile = File(..., description="CSV file with columns: lat, long, center_freq_hz, bandwidth_hz, label"),
):
    """Upload assignments CSV and store in MinIO."""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    # Read and validate CSV
    try:
        contents = await file.read()
        df = pd.read_csv(io.BytesIO(contents))
        
        # Validate required columns
        required_cols = {"lat", "long", "center_freq_hz", "bandwidth_hz", "label"}
        if not required_cols.issubset(df.columns):
            missing = required_cols - set(df.columns)
            raise HTTPException(
                status_code=400,
                detail=f"Missing required columns: {', '.join(missing)}. Found: {', '.join(df.columns)}"
            )
        
        # Validate data types
        try:
            df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
            df["long"] = pd.to_numeric(df["long"], errors="coerce")
            df["center_freq_hz"] = pd.to_numeric(df["center_freq_hz"], errors="coerce")
            df["bandwidth_hz"] = pd.to_numeric(df["bandwidth_hz"], errors="coerce")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid numeric data: {e}")
        
        if df[["lat", "long", "center_freq_hz", "bandwidth_hz"]].isna().any().any():
            raise HTTPException(status_code=400, detail="Numeric columns (lat, long, center_freq_hz, bandwidth_hz) must contain valid numbers")
        
        # Write back to CSV string
        output = io.StringIO()
        df[list(required_cols)].to_csv(output, index=False)
        csv_bytes = output.getvalue().encode("utf-8")
        
    except pd.errors.EmptyDataError:
        raise HTTPException(status_code=400, detail="CSV file is empty")
    except pd.errors.ParserError as e:
        raise HTTPException(status_code=400, detail=f"Invalid CSV format: {e}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error processing CSV: {e}")

    # Upload to MinIO
    try:
        client = get_minio_client()
        bucket = bucket_name()
        obj_path = _assignments_path(location, month)
        
        client.put_object(
            bucket,
            obj_path,
            io.BytesIO(csv_bytes),
            length=len(csv_bytes),
            content_type="text/csv",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload to MinIO: {e}")

    return jsonable_encoder({
        "message": "Assignments uploaded successfully",
        "location": location,
        "month": month,
        "rows": len(df),
        "path": obj_path,
    })


@router.get("")
def get_assignments(
    location: str = Query(..., description="Location"),
    month: str = Query(..., description="Month in YYYY-MM format"),
):
    """Fetch assignments CSV from MinIO and return as JSON array."""
    try:
        client = get_minio_client()
        bucket = bucket_name()
        obj_path = _assignments_path(location, month)
        
        try:
            response = client.get_object(bucket, obj_path)
            csv_data = response.read()
            response.close()
            response.release_conn()
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Assignments file not found: {e}")

        # Parse CSV
        try:
            df = pd.read_csv(io.BytesIO(csv_data))
            # Convert to list of dicts
            assignments = df.to_dict(orient="records")
            # Ensure numeric types
            for a in assignments:
                a["lat"] = float(a["lat"])
                a["long"] = float(a["long"])
                a["center_freq_hz"] = float(a["center_freq_hz"])
                a["bandwidth_hz"] = float(a["bandwidth_hz"])
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error parsing CSV: {e}")

        return jsonable_encoder({"location": location, "month": month, "assignments": assignments})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch assignments: {e}")


@router.post("")
async def create_assignment(
    location: str = Query(..., description="Location"),
    month: str = Query(..., description="Month in YYYY-MM format"),
    assignment: AssignmentCreate = Body(..., description="Assignment data"),
):
    """Add a single assignment to existing CSV (or create new if doesn't exist)."""
    try:
        client = get_minio_client()
        bucket = bucket_name()
        obj_path = _assignments_path(location, month)
        
        # Try to read existing CSV, or create empty DataFrame if doesn't exist
        try:
            response = client.get_object(bucket, obj_path)
            csv_data = response.read()
            response.close()
            response.release_conn()
            df = pd.read_csv(io.BytesIO(csv_data))
        except Exception:
            # File doesn't exist, create new DataFrame with required columns
            df = pd.DataFrame(columns=["lat", "long", "center_freq_hz", "bandwidth_hz", "label"])
        
        # Validate assignment data
        required_cols = {"lat", "long", "center_freq_hz", "bandwidth_hz", "label"}
        if not required_cols.issubset(df.columns):
            raise HTTPException(
                status_code=400,
                detail=f"Existing CSV has invalid columns. Expected: {', '.join(required_cols)}"
            )
        
        # Validate numeric values
        try:
            lat = float(assignment.lat)
            long = float(assignment.long)
            center_freq_hz = float(assignment.center_freq_hz)
            bandwidth_hz = float(assignment.bandwidth_hz)
            if bandwidth_hz <= 0:
                raise HTTPException(status_code=400, detail="bandwidth_hz must be positive")
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=400, detail=f"Invalid numeric data: {e}")
        
        # Add new assignment
        new_row = {
            "lat": lat,
            "long": long,
            "center_freq_hz": center_freq_hz,
            "bandwidth_hz": bandwidth_hz,
            "label": assignment.label,
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        
        # Write back to CSV
        output = io.StringIO()
        df[list(required_cols)].to_csv(output, index=False)
        csv_bytes = output.getvalue().encode("utf-8")
        
        client.put_object(
            bucket,
            obj_path,
            io.BytesIO(csv_bytes),
            length=len(csv_bytes),
            content_type="text/csv",
        )
        
        # Return updated assignments list
        assignments = df.to_dict(orient="records")
        for a in assignments:
            a["lat"] = float(a["lat"])
            a["long"] = float(a["long"])
            a["center_freq_hz"] = float(a["center_freq_hz"])
            a["bandwidth_hz"] = float(a["bandwidth_hz"])
        
        return jsonable_encoder({"location": location, "month": month, "assignments": assignments})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create assignment: {e}")


@router.delete("")
async def delete_assignment(
    location: str = Query(..., description="Location"),
    month: str = Query(..., description="Month in YYYY-MM format"),
    assignment: AssignmentDelete = Body(..., description="Assignment identifier (center_freq_hz, bandwidth_hz)"),
):
    """Delete an assignment from CSV by matching center_freq_hz and bandwidth_hz."""
    try:
        client = get_minio_client()
        bucket = bucket_name()
        obj_path = _assignments_path(location, month)
        
        # Read existing CSV
        try:
            response = client.get_object(bucket, obj_path)
            csv_data = response.read()
            response.close()
            response.release_conn()
            df = pd.read_csv(io.BytesIO(csv_data))
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Assignments file not found: {e}")
        
        # Validate required columns
        required_cols = {"lat", "long", "center_freq_hz", "bandwidth_hz", "label"}
        if not required_cols.issubset(df.columns):
            raise HTTPException(
                status_code=400,
                detail=f"CSV has invalid columns. Expected: {', '.join(required_cols)}"
            )
        
        # Convert to numeric for comparison
        df["center_freq_hz"] = pd.to_numeric(df["center_freq_hz"], errors="coerce")
        df["bandwidth_hz"] = pd.to_numeric(df["bandwidth_hz"], errors="coerce")
        
        # Match assignment (use small tolerance for floating point comparison)
        target_center = float(assignment.center_freq_hz)
        target_bandwidth = float(assignment.bandwidth_hz)
        tolerance = 1e-6  # 1 microHz tolerance
        
        mask = (
            ((df["center_freq_hz"] - target_center).abs() < tolerance) &
            ((df["bandwidth_hz"] - target_bandwidth).abs() < tolerance)
        )
        
        if not mask.any():
            raise HTTPException(
                status_code=404,
                detail=f"Assignment not found with center_freq_hz={target_center} and bandwidth_hz={target_bandwidth}"
            )
        
        # Remove matching assignment(s)
        df = df[~mask].reset_index(drop=True)
        
        # Write back to CSV
        output = io.StringIO()
        df[list(required_cols)].to_csv(output, index=False)
        csv_bytes = output.getvalue().encode("utf-8")
        
        client.put_object(
            bucket,
            obj_path,
            io.BytesIO(csv_bytes),
            length=len(csv_bytes),
            content_type="text/csv",
        )
        
        # Return updated assignments list
        assignments = df.to_dict(orient="records")
        for a in assignments:
            a["lat"] = float(a["lat"])
            a["long"] = float(a["long"])
            a["center_freq_hz"] = float(a["center_freq_hz"])
            a["bandwidth_hz"] = float(a["bandwidth_hz"])
        
        return jsonable_encoder({"location": location, "month": month, "assignments": assignments})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete assignment: {e}")

