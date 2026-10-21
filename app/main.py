from __future__ import annotations

import re
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import accounts, billing, db
from .config import settings
from .providers import provider_status
from . import worker


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    accounts.init_db()
    worker.start()
    yield


STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
app = FastAPI(title="Transcription Dashboard", lifespan=lifespan)


@app.get("/api/providers")
def providers():
    return provider_status()


@app.get("/api/ads/config")
def ads_config():
    """Ad presence flag for the SPA (never exposes keys; the script itself
    loads from Google only when a client id is configured)."""
    return {"enabled": bool(settings.adsense_client), "client": settings.adsense_client or None}


@app.get("/ads.txt", response_class=PlainTextResponse)
def ads_txt():
    """Serve ads.txt at the domain root when configured (AdSense recommends it)."""
    if not settings.ads_txt:
        raise HTTPException(404, "ads.txt not configured")
    return PlainTextResponse(settings.ads_txt)


@app.post("/api/jobs", status_code=202)
async def create_job(file: UploadFile = File(...), language: str = Form(""),
                     mode: str = Form(""), authorization: str = Header("")):
    user = billing.resolve_user_from_header(authorization) if accounts.enabled() else None
    if accounts.enabled() and user:
        bal = user["balance"]
        if bal < 1.0:
            raise HTTPException(402, "No credits left. Buy more from the Pricing page.")
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
    db.create_job(job_id, file.filename or dest.name, language.strip() or None,
                  user_id=user["id"] if user else None,
                  mode=(mode.strip().lower() if mode.strip().lower() in ("full", "budget")
                        else settings.default_mode))
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


# ------------------------------------------------------------------ accounts

@app.get("/api/billing/config")
def billing_config():
    """Whether accounts/payments are live + bundle list for the pricing page."""
    return {
        "enabled": accounts.enabled(),
        "bundles": billing.bundles() if accounts.enabled() else [],
        "free_minutes": settings.free_minutes if accounts.enabled() else None,
        "razorpay_available": bool(settings.razorpay_key_id),
    }


@app.post("/api/auth/signup")
def auth_signup(email: str = Form(...), password: str = Form(...)):
    if not accounts.enabled():
        raise HTTPException(404, "Accounts are disabled on this deployment")
    try:
        u = accounts.signup(email, password)
    except ValueError as e:
        raise HTTPException(400, str(e))
    token = accounts.login(email, password)
    return {"token": token, **u}


@app.post("/api/auth/login")
def auth_login(email: str = Form(...), password: str = Form(...)):
    if not accounts.enabled():
        raise HTTPException(404, "Accounts are disabled on this deployment")
    try:
        token = accounts.login(email, password)
    except ValueError as e:
        raise HTTPException(401, str(e))
    u = accounts.user_for_token(token)
    return {"token": token, **u}


@app.post("/api/auth/logout")
def auth_logout(authorization: str = Header("")):
    token = authorization.removeprefix("Bearer ").strip()
    if token:
        accounts.logout(token)
    return {"ok": True}


@app.get("/api/auth/me")
def auth_me(authorization: str = Header("")):
    u = billing.resolve_user_from_header(authorization)
    if not u:
        raise HTTPException(401, "Not signed in")
    return u


@app.get("/api/auth/ledger")
def auth_ledger(authorization: str = Header("")):
    u = billing.resolve_user_from_header(authorization)
    if not u:
        raise HTTPException(401, "Not signed in")
    return ledger_shape(accounts.ledger(u["id"]))


def ledger_shape(rows: list[dict]) -> list[dict]:
    for r in rows:
        r["created_at"] = int(r["created_at"])
    return rows


# ------------------------------------------------------------------ billing

@app.post("/api/billing/order")
def billing_order(bundle: str = Form(...), authorization: str = Header("")):
    u = billing.resolve_user_from_header(authorization)
    if not u:
        raise HTTPException(401, "Sign in to buy credits")
    try:
        return billing.create_order(u["id"], bundle)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@app.post("/api/billing/verify")
async def billing_verify(request: Request, authorization: str = Header("")):
    """Browser checkout handler posts the Razorpay response here."""
    u = billing.resolve_user_from_header(authorization)
    if not u:
        raise HTTPException(401, "Not signed in")
    form = await request.form()
    try:
        out = billing.verify_checkout(
            (form.get("order") or "").strip(),
            (form.get("razorpay_order_id") or "").strip(),
            (form.get("razorpay_payment_id") or "").strip(),
            (form.get("razorpay_signature") or "").strip(),
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return out


@app.post("/api/billing/webhook")
async def billing_webhook(request: Request):
    raw = await request.body()
    sig = request.headers.get("X-Razorpay-Signature", "")
    try:
        return billing.handle_webhook(raw, sig)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))


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


@app.delete("/api/jobs")
def clear_history():
    """Clear every finished/failed job (running ones keep going)."""
    running = {r["id"] for r in db.list_jobs() if r["status"] in ("queued", "processing")}
    removed = db.delete_all_jobs(skip_running=bool(running))
    for job_id in removed:
        shutil.rmtree(settings.upload_dir(job_id), ignore_errors=True)
    return {"deleted": removed, "skipped_running": len(running)}


# The built React app. Mounted last so the /api routes above take priority.
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="ui")
