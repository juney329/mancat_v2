from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..services.dataset import DatasetService, get_dataset_service

router = APIRouter(prefix="/bands", tags=["markers"])


class Marker(BaseModel):
    id: str = Field(..., description="Client assigned identifier")
    freq: float = Field(..., description="Frequency in Hz")
    label: str = Field(default="", description="Display label")
    color: str = Field(default="#ff0000", description="CSS color string")
    width: float = Field(default=0.0, description="Optional region width (Hz)")


class MarkersPayload(BaseModel):
    markers: List[Marker]


@router.get("/{band_id}/markers", response_model=MarkersPayload)
def get_markers(
    band_id: str,
    service: DatasetService = Depends(get_dataset_service),
) -> MarkersPayload:
    band = service.get_band(band_id)
    payload = [Marker(**marker) for marker in band.load_markers()]
    return MarkersPayload(markers=payload)


@router.post("/{band_id}/markers", response_model=MarkersPayload)
def save_markers(
    band_id: str,
    payload: MarkersPayload,
    service: DatasetService = Depends(get_dataset_service),
) -> MarkersPayload:
    band = service.get_band(band_id)
    serialized = [marker.dict() for marker in payload.markers]
    band.save_markers(serialized)
    return payload
