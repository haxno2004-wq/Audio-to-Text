from __future__ import annotations

import re
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import db
from .config import settings
from .providers import provider_status
from . import worker


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    worker.start()
    yield


STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
app = FastAPI(title="Transcription Dashboard", lifespan=lifespan)


@app.get("/api/providers")
def providers():
    return provider_status()


@app.post("/api/jobs", status_code=202)
async def create_job(file: UploadFile = File(...), language: str = Form("")):
    job_id = uuid.uuid4().hex[:12]
    suffix = re.sub(r"[^.a-z0-9]", "", Path(file.filename or "").suffix.lower())[:10] or ".bin"
    folder = settings.upload_dir(job_id)
    folder.mkdir(parents=True)
    dest = folder / f"original{suffix}"
    limit = settings.max_upload_mb * 1024 * 1024
    size, too_big = 0, False
    with dest.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                too_big = True
                break
            await run_in_threadpool(out.write, chunk)
    if too_big or size == 0:
        shutil.rmtree(folder, ignore_errors=True)
        if too_big:
            raise HTTPException(413, f"File is larger than {settings.max_upload_mb} MB")
        raise HTTPException(400, "The uploaded file is empty")
    db.create_job(job_id, file.filename or dest.name, language.strip() or None)
    worker.enqueue(job_id)
    return {"id": job_id, "status": "queued"}


@app.get("/api/jobs")
def list_jobs():
    return db.list_jobs()


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.get("/api/jobs/{job_id}/transcript.txt", response_class=PlainTextResponse)
def download_transcript(job_id: str):
    job = db.get_job(job_id)
    if not job or job["status"] != "done":
        raise HTTPException(404, "Transcript not ready")
    name = re.sub(r"[^\w.-]+", "_", Path(job["filename"]).stem) or "transcript"
    return PlainTextResponse(job["final_text"], headers={"Content-Disposition": f'attachment; filename="{name}.txt"'})


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] in ("queued", "processing"):
        raise HTTPException(409, "This job is still running")
    db.delete_job(job_id)
    shutil.rmtree(settings.upload_dir(job_id), ignore_errors=True)
    return {"deleted": job_id}


# The built React app. Mounted last so the /api routes above take priority.
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="ui")
