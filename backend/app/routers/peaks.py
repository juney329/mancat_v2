from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from scipy.signal import find_peaks

from ..services.dataset import DatasetService, get_dataset_service

router = APIRouter(prefix="/bands", tags=["peaks"])


class PeakRequest(BaseModel):
    curve: str = Field(..., description="Summary curve to analyse (e.g. Avg, Max)")
    height: Optional[float] = Field(default=None, ge=0)
    prominence: Optional[float] = Field(default=None, ge=0)
    distance: Optional[int] = Field(default=None, ge=1)
    f0: Optional[float] = Field(default=None)
    f1: Optional[float] = Field(default=None)


class PeakItem(BaseModel):
    freq: float
    value: float
    properties: Dict[str, float]


class PeakResponse(BaseModel):
    peaks: List[PeakItem]


@router.post("/{band_id}/peaks", response_model=PeakResponse)
def find_band_peaks(
    band_id: str,
    request: PeakRequest,
    service: DatasetService = Depends(get_dataset_service),
) -> PeakResponse:
    band = service.get_band(band_id)
    freqs, values = band.peak_candidates(
        curve=request.curve, f0=request.f0, f1=request.f1
    )

    kwargs = {
        key: value
        for key, value in {
            "height": request.height,
            "prominence": request.prominence,
            "distance": request.distance,
        }.items()
        if value is not None
    }

    indices, properties = find_peaks(values, **kwargs)
    peaks: List[PeakItem] = []
    for idx in indices:
        peak_freq = float(freqs[idx])
        peak_value = float(values[idx])
        peak_props: Dict[str, float] = {}
        for key, val in properties.items():
            if isinstance(val, (list, tuple, np.ndarray)):
                arr = np.asarray(val)
                if arr.ndim == 0:
                    peak_props[key] = float(arr)
                else:
                    peak_props[key] = float(arr[min(idx, arr.shape[0] - 1)])
            else:
                peak_props[key] = float(val)
        peaks.append(PeakItem(freq=peak_freq, value=peak_value, properties=peak_props))

    return PeakResponse(peaks=peaks)
