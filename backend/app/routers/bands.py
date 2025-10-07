from __future__ import annotations

import io
from typing import Dict, List, Optional

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from ..services.dataset import DatasetService, get_dataset_service

router = APIRouter(prefix="/bands", tags=["bands"])
@router.get("", response_model=List[Dict[str, object]])
def list_bands(service: DatasetService = Depends(get_dataset_service)) -> List[Dict[str, object]]:
    bands = service.available_bands()
    return [
        {
            "id": info.band_id,
            "meta": info.meta,
        }
        for info in bands
    ]


@router.get("/{band_id}/meta")
def get_band_meta(band_id: str, service: DatasetService = Depends(get_dataset_service)) -> Dict[str, object]:
    try:
        band = service.get_band(band_id)
    except KeyError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return dict(band.meta)


@router.get("/{band_id}/summary")
def get_band_summary(
    band_id: str,
    f0: Optional[float] = Query(default=None),
    f1: Optional[float] = Query(default=None),
    max_pts: int = Query(default=2200, ge=1),
    service: DatasetService = Depends(get_dataset_service),
) -> Dict[str, List[float]]:
    band = service.get_band(band_id)
    summary = band.summary_slice(f0=f0, f1=f1, max_points=max_pts)
    return {key: np.asarray(value).tolist() for key, value in summary.items()}


def _encode_png(tile: np.ndarray) -> bytes:
    from PIL import Image

    data = tile
    min_val = float(np.min(data))
    max_val = float(np.max(data))
    if max_val - min_val < 1e-6:
        max_val = min_val + 1e-6
    norm = (data - min_val) / (max_val - min_val)
    buf = io.BytesIO()
    img = Image.fromarray(np.clip(norm * 255.0, 0, 255).astype(np.uint8), mode="L")
    img.save(buf, format="PNG")
    return buf.getvalue()


@router.get("/{band_id}/waterfall_tile")
def get_waterfall_tile(
    band_id: str,
    f0: Optional[float] = Query(default=None),
    f1: Optional[float] = Query(default=None),
    t0: Optional[float] = Query(default=None),
    t1: Optional[float] = Query(default=None),
    maxw: int = Query(default=1600, ge=1),
    maxt: int = Query(default=600, ge=1),
    fmt: str = Query(default="png"),
    service: DatasetService = Depends(get_dataset_service),
) -> Response:
    band = service.get_band(band_id)
    tile, times, freqs = band.waterfall_tile(
        f0=f0, f1=f1, t0=t0, t1=t1, maxw=maxw, maxt=maxt
    )

    headers = {
        "X-Time-Start": str(float(times[0]) if len(times) else 0.0),
        "X-Time-End": str(float(times[-1]) if len(times) else 0.0),
        "X-Freq-Start": str(float(freqs[0]) if len(freqs) else 0.0),
        "X-Freq-End": str(float(freqs[-1]) if len(freqs) else 0.0),
    }

    if fmt == "png":
        payload = _encode_png(tile)
        return Response(content=payload, media_type="image/png", headers=headers)

    buf = io.BytesIO()
    np.savez_compressed(buf, tile=tile, times=times, freqs=freqs)
    return Response(content=buf.getvalue(), media_type="application/octet-stream", headers=headers)
