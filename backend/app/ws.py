from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from .services.dataset import DatasetService, get_dataset_service

router = APIRouter()


@router.websocket("/ws/bands/{band_id}")
async def band_playback(
    websocket: WebSocket,
    band_id: str,
    service: DatasetService = Depends(get_dataset_service),
) -> None:
    await websocket.accept()
    params = websocket.query_params
    window_s = float(params.get("window_s", 10.0))
    fps = float(params.get("fps", 4.0))
    if fps <= 0:
        fps = 1.0

    band = service.get_band(band_id)
    times = band.times
    start_unix = float(band.meta.get("start_unix", time.time()))

    if len(times) == 0:
        await websocket.send_json({"t0": 0.0, "t1": 0.0, "cursor_unix": start_unix})
        await websocket.close()
        return

    index = 0
    interval = 1.0 / fps
    try:
        while True:
            cursor = float(times[min(index, len(times) - 1)])
            t1 = cursor
            t0 = max(times[0], t1 - window_s)
            payload = {"t0": float(t0), "t1": float(t1), "cursor_unix": start_unix + cursor}
            await websocket.send_json(payload)
            index = (index + 1) % len(times)
            await asyncio.sleep(interval)
    except WebSocketDisconnect:  # pragma: no cover - fastapi handles disconnects
        return
