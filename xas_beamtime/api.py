from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import load_config
from .models import RuntimeLimits
from .service import BeamtimeService


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT))
CONFIG_PATH = Path(os.environ.get("XAS_CONFIG", PROJECT_ROOT / "config" / "app.yaml"))
if not CONFIG_PATH.exists():
    CONFIG_PATH = PROJECT_ROOT / "config" / "app.example.yaml"


class WatchRequest(BaseModel):
    folder: str
    maximum_scans: int | None = Field(default=None, ge=1)
    maximum_time_seconds: float | None = Field(default=None, gt=0)
    averaging_mode: str = Field(pattern="^(equal|noise_weighted)$")


class ReanalysisRequest(BaseModel):
    sample_id: str
    averaging_mode: str = Field(pattern="^(equal|noise_weighted)$")
    included_scan_ids: list[str] | None = None
    anchors: dict[str, list[float]] | None = None


class ReviewRequest(BaseModel):
    analysis_id: str
    sample_id: str
    rating: str = Field(pattern="^(Q-ready|QL-ready|Below-QL)$")
    override_recommendation: str | None = None
    averaging_mode: str = Field(pattern="^(equal|noise_weighted)$")
    included_scans: list[str]
    excluded_scans: list[str]
    glitch_decisions: list[dict[str, Any]] = Field(default_factory=list)
    local_normalization_anchors: dict[str, list[float]] = Field(default_factory=dict)
    notes: str = ""
    reviewer: str | None = None
    reviewer_role: str = Field(
        default="beamline_user",
        pattern="^(beamline_user|beamline_scientist|pi_experiment_lead|other)$",
    )


def create_app() -> FastAPI:
    service = BeamtimeService(load_config(CONFIG_PATH))

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        service.start()
        yield
        service.stop()

    app = FastAPI(title="Real-time XAS Beamtime Decision Framework", version="0.2.0", lifespan=lifespan)
    app.state.beamtime = service

    @app.get("/api/state")
    def state() -> dict[str, Any]:
        return service.state()

    @app.post("/api/watch")
    def watch(request: WatchRequest) -> dict[str, Any]:
        folder = Path(request.folder).expanduser()
        try:
            service.set_watch(
                folder,
                RuntimeLimits(request.maximum_scans, request.maximum_time_seconds),
                request.averaging_mode,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return service.state()

    @app.post("/api/select-folder")
    def select_folder(x_xas_local: Annotated[str | None, Header()] = None) -> dict[str, Any]:
        """Open the operating system folder picker for this local-only application."""
        if x_xas_local != "1":
            raise HTTPException(status_code=403, detail="Local application header required")
        try:
            from .folder_dialog import select_directory
            selected = select_directory(service.watch_folder)
        except RuntimeError as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc
        return {"folder": str(selected) if selected else None, "cancelled": selected is None}

    @app.post("/api/reanalyze")
    def reanalyze(request: ReanalysisRequest) -> dict[str, Any]:
        try:
            return service.reanalyze(
                request.sample_id, request.averaging_mode,
                set(request.included_scan_ids) if request.included_scan_ids is not None else None,
                request.anchors,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown sample: {request.sample_id}") from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/reviews")
    def save_review(request: ReviewRequest) -> dict[str, str]:
        try:
            return {"review_id": service.save_review(request.model_dump())}
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/reviews")
    def reviews() -> list[dict[str, Any]]:
        return service.storage.recent_reviews()

    @app.get("/api/references")
    def references() -> dict[str, Any]:
        return service.references.manifest(service.profile.get("references.manifest_filename", "references.yaml"))

    frontend = BUNDLE_ROOT / "frontend" / "dist"
    if frontend.exists():
        assets = frontend / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            requested = frontend / path
            if path and requested.is_file():
                return FileResponse(requested)
            return FileResponse(frontend / "index.html")

    return app


app = create_app()
