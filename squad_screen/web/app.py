from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from squad_screen.logging_setup import setup_logging
from squad_screen.pipeline import run_screen
from squad_screen.report.writer import report_to_dict

setup_logging()

ROOT = Path(__file__).resolve().parent
TEMPLATES = ROOT / "templates"
STATIC = ROOT / "static"

app = FastAPI(title="Squad Screen", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")

JobStatus = Literal["queued", "running", "done", "error"]


class ScreenRequest(BaseModel):
    team: str = Field(min_length=2)
    mode: Literal["demo", "live"] = "demo"
    days: int = Field(default=3, ge=1, le=7)


class Job(BaseModel):
    id: str
    status: JobStatus
    message: str = ""
    result: dict[str, Any] | None = None
    error: str | None = None
    markdown_path: str | None = None
    json_path: str | None = None


JOBS: dict[str, Job] = {}


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse((TEMPLATES / "index.html").read_text(encoding="utf-8"))


@app.post("/api/screen")
async def start_screen(payload: ScreenRequest) -> Job:
    job_id = uuid.uuid4().hex[:12]
    job = Job(id=job_id, status="queued", message="Queued")
    JOBS[job_id] = job

    async def _run() -> None:
        job.status = "running"
        job.message = "Starting…"

        async def progress(message: str) -> None:
            job.message = message

        try:
            report, md_path, json_path = await run_screen(
                payload.team,
                mode=payload.mode,
                lookback_days=payload.days,
                progress=progress,
            )
            job.result = report_to_dict(report)
            job.markdown_path = str(md_path)
            job.json_path = str(json_path)
            job.status = "done"
            job.message = "Complete"
        except Exception as exc:  # noqa: BLE001
            job.status = "error"
            job.error = f"{type(exc).__name__}: {exc}"
            job.message = "Failed"

    asyncio.create_task(_run())
    return job


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> Job:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Unknown job")
    return job


@app.get("/api/reports/latest.md")
async def latest_md() -> FileResponse:
    path = Path("reports/latest.md")
    if not path.exists():
        raise HTTPException(status_code=404, detail="No report yet")
    return FileResponse(path, media_type="text/markdown", filename="squad-screen.md")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
