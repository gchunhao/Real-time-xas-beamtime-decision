from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import load_config
from .models import RuntimeLimits, ScanDisposition
from .service import BeamtimeService


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(os.environ.get("XAS_CONFIG", PROJECT_ROOT / "config" / "app.yaml"))
if not CONFIG_PATH.exists():
    CONFIG_PATH = PROJECT_ROOT / "config" / "app.example.yaml"


class WatchRequest(BaseModel):
    folder: str
    maximum_scans: int | None = Field(default=None, ge=1)
    maximum_time_seconds: float | None = Field(default=None, gt=0)
    averaging_mode: str = Field(pattern="^(equal|noise_weighted)$")


class OfflineImportRequest(BaseModel):
    paths: list[str] = Field(min_length=1)
    recursive: bool = True
    maximum_scans: int | None = Field(default=None, ge=1)
    maximum_time_seconds: float | None = Field(default=None, gt=0)
    averaging_mode: str = Field(default="equal", pattern="^(equal|noise_weighted)$")


class ReanalysisRequest(BaseModel):
    sample_id: str
    averaging_mode: str = Field(pattern="^(equal|noise_weighted)$")
    included_scan_ids: list[str] | None = None
    anchors: dict[str, list[float]] | None = None


class ReviewRequest(BaseModel):
    analysis_id: str
    sample_id: str
    rating: str = Field(pattern="^(Q-ready|QL-ready|Below-QL|QC-blocked)$")
    override_recommendation: str | None = Field(
        default=None, pattern="^(CONTINUE|STOP|REACQUIRE|REVIEW_REQUIRED)$"
    )
    averaging_mode: str = Field(pattern="^(equal|noise_weighted)$")
    included_scans: list[str]
    excluded_scans: list[str]
    glitch_decisions: list[dict[str, Any]] = Field(default_factory=list)
    local_normalization_anchors: dict[str, list[float]] = Field(default_factory=dict)
    notes: str = ""
    reviewer: str | None = None
    reviewer_role: str = Field(
        default="User",
        pattern="^(User|Beamline Scientist|PI|Postdoc|Student|Operator|Other)$",
    )
    reviewer_level: int = Field(default=0, ge=0)
    review_context: str = Field(default="LIVE", pattern="^(LIVE|RETROSPECTIVE_BLIND|HINDSIGHT)$")


class ScanDispositionRequest(BaseModel):
    disposition: str = Field(pattern="^(USABLE|SUSPECT|EXCLUDED_FROM_USABLE_COUNT|PENDING_REVIEW)$")
    reason: str | None = None
    replacement_for_scan_id: str | None = None


class SampleArchiveRequest(BaseModel):
    archived: bool
    reason: str | None = Field(default=None, max_length=500)


def create_app() -> FastAPI:
    service = BeamtimeService(load_config(CONFIG_PATH))

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        service.start()
        try:
            yield
        finally:
            service.close()

    app = FastAPI(title="Real-time XAS Beamtime Decision Framework", version="0.2.1", lifespan=lifespan)
    app.state.beamtime = service

    # Backward-compatible v0.1/v0.2 dashboard endpoints.
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

    @app.post("/api/import/offline")
    def import_offline(request: OfflineImportRequest) -> dict[str, Any]:
        try:
            return service.import_offline(
                request.paths,
                RuntimeLimits(request.maximum_scans, request.maximum_time_seconds),
                request.averaging_mode,
                recursive=request.recursive,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/import/demo")
    def import_demo() -> dict[str, Any]:
        try:
            return service.import_offline(
                [service.config.path("watch.folder", "./test_data/incoming")],
                service.config.limits,
                str(service.config.get("analysis.averaging_mode", "equal")),
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/reanalyze")
    def reanalyze(request: ReanalysisRequest) -> dict[str, Any]:
        try:
            return service.reanalyze(
                request.sample_id,
                request.averaging_mode,
                set(request.included_scan_ids) if request.included_scan_ids is not None else None,
                request.anchors,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown sample: {request.sample_id}") from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Resource-style v0.2 contracts.
    @app.get("/api/projects")
    def projects() -> list[dict[str, Any]]:
        return service.projects()

    @app.get("/api/projects/{project_id}")
    def project(project_id: str) -> dict[str, Any]:
        row = service.storage.get_project(project_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Unknown project")
        row["sessions"] = service.sessions(project_id)
        return row

    @app.get("/api/sessions")
    def sessions(project_id: str | None = None) -> list[dict[str, Any]]:
        return service.sessions(project_id)

    @app.get("/api/sessions/{session_id}")
    def session(session_id: str) -> dict[str, Any]:
        row = service.storage.get_session(session_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Unknown session")
        row["samples"] = service.samples(session_id)
        return row

    @app.get("/api/samples")
    def samples(session_id: str | None = None, archived: bool = False) -> list[dict[str, Any]]:
        return service.samples(session_id, archived=archived)

    @app.get("/api/samples/{sample_id}")
    def sample(sample_id: str) -> dict[str, Any]:
        try:
            return service.sample(sample_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown sample") from exc

    @app.patch("/api/samples/{sample_id}/archive")
    def archive_sample(sample_id: str, request: SampleArchiveRequest) -> dict[str, Any]:
        try:
            return service.set_sample_archived(sample_id, request.archived, request.reason)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown sample") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/samples/{sample_id}/scans")
    def sample_scans(sample_id: str) -> list[dict[str, Any]]:
        if service.storage.get_sample(sample_id) is None:
            raise HTTPException(status_code=404, detail="Unknown sample")
        return service.scans(sample_id)

    @app.get("/api/samples/{sample_id}/decisions")
    def sample_decisions(sample_id: str, limit: int = 100) -> list[dict[str, Any]]:
        if service.storage.get_sample(sample_id) is None:
            raise HTTPException(status_code=404, detail="Unknown sample")
        return service.storage.list_decisions(sample_id, max(1, min(limit, 1000)))

    @app.get("/api/samples/{sample_id}/spectrum")
    def sample_spectrum(sample_id: str) -> dict[str, Any]:
        try:
            return service.sample_spectrum(sample_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Sample spectrum is unavailable") from exc

    @app.get("/api/scans")
    def scans(sample_id: str | None = None) -> list[dict[str, Any]]:
        return service.scans(sample_id)

    @app.get("/api/scans/{scan_id}")
    def scan(scan_id: str) -> dict[str, Any]:
        try:
            return service.scan(scan_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown scan") from exc

    @app.get("/api/scans/{scan_id}/spectrum")
    def scan_spectrum(scan_id: str) -> dict[str, Any]:
        try:
            return service.scan_spectrum(scan_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Scan spectrum is not loaded in the current runtime") from exc

    @app.patch("/api/scans/{scan_id}/disposition")
    def set_scan_disposition(scan_id: str, request: ScanDispositionRequest) -> dict[str, Any]:
        try:
            return service.set_scan_disposition(
                scan_id,
                ScanDisposition(request.disposition),
                request.reason,
                request.replacement_for_scan_id,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown scan") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/decisions")
    def decisions(sample_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        return service.storage.list_decisions(sample_id, max(1, min(limit, 1000)))

    @app.get("/api/decisions/{decision_id}")
    def decision(decision_id: str) -> dict[str, Any]:
        row = service.storage.get_decision(decision_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Unknown decision")
        return row

    @app.post("/api/reviews")
    def save_review(request: ReviewRequest) -> dict[str, str]:
        try:
            return {"review_id": service.save_review(request.model_dump())}
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/reviews")
    def reviews(limit: int = 100) -> list[dict[str, Any]]:
        return service.storage.recent_reviews(max(1, min(limit, 1000)))

    @app.get("/api/review-queue")
    def review_queue(status: str | None = "PENDING", limit: int = 100) -> list[dict[str, Any]]:
        allowed = {None, "PENDING", "RESOLVED", "SUPERSEDED"}
        if status not in allowed:
            raise HTTPException(status_code=400, detail="Invalid review queue status")
        return service.storage.review_queue(status, max(1, min(limit, 1000)))

    @app.get("/api/references")
    def references() -> dict[str, Any]:
        return service.references.manifest(service.profile.get("references.manifest_filename", "references.yaml"))

    @app.get("/api/audit-events")
    @app.get("/api/audit")
    def audit_events(limit: int = 100) -> list[dict[str, Any]]:
        return service.storage.recent_audit_events(limit=max(1, min(limit, 1000)))

    @app.get("/api/scheduler/state")
    def scheduler_state() -> dict[str, Any]:
        return service.scheduler.state()

    @app.get("/api/workflow")
    def workflow_projection() -> dict[str, Any]:
        return service.workflow_projection()

    frontend = PROJECT_ROOT / "frontend" / "dist"
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
