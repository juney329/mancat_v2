from __future__ import annotations

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import bands, markers, peaks
from .ws import router as ws_router


def create_app() -> FastAPI:
    app = FastAPI(title="RF Spectrum Backend")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[os.getenv("FRONTEND_ORIGIN", "*")],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(bands.router)
    app.include_router(peaks.router)
    app.include_router(markers.router)
    app.include_router(ws_router)

    return app


app = create_app()
