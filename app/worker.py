"""
Background job runner. Replaces Celery + Redis: one daemon thread takes job ids off an
in-memory queue, so jobs run one at a time and the Whisper model stays loaded.
Jobs that were queued or running when the app stopped are re-queued on the next start.
"""
from __future__ import annotations

import json
import logging
import queue
import shutil
import threading

from . import accounts, audio, db
from .config import settings
from .consensus import build_consensus
from .polish import polish
from .orchestrator import run_all

log = logging.getLogger(__name__)
_queue: "queue.Queue[str]" = queue.Queue()
_started = False


def enqueue(job_id: str) -> None:
    _queue.put(job_id)


def start() -> None:
    global _started
    if _started:
        return
    _started = True
    for job_id in db.reset_unfinished():
        _queue.put(job_id)
    threading.Thread(target=_loop, name="transcribe-worker", daemon=True).start()


def _loop() -> None:
    while True:
        job_id = _queue.get()
        try:
            run_job(job_id)
        except Exception:
            log.exception("Worker crashed on job %s", job_id)
        finally:
            _queue.task_done()


def run_job(job_id: str) -> None:
    job = db.get_job(job_id)
    if not job or job["status"] == "done":
        return
    user_id = job.get("user_id") if accounts.enabled() else None
    mode = job.get("mode") or None
    work = settings.work_dir(job_id)
    try:
        db.update_job(job_id, status="processing", stage="Preparing audio", progress=0.02)
        src = next(settings.upload_dir(job_id).glob("original*"))
        work.mkdir(parents=True, exist_ok=True)
        norm = audio.normalize(src, work / "audio.flac")
        duration = audio.probe_duration(norm)
        db.update_job(job_id, duration=duration, stage="Transcribing", progress=0.06)

        results, errors = run_all(
            norm, duration, job["language_hint"], mode=mode,
            sink=lambda p: db.update_job(job_id, progress=round(0.06 + 0.84 * p, 3)),
        )
        if not results:
            detail = "; ".join(f"{e['label']}: {e['error']}" for e in errors)
            raise RuntimeError(f"Every model failed. {detail}")

        db.update_job(job_id, stage="Finalizing", progress=0.92)
        merged = build_consensus(results, settings.weights, settings.window_seconds)

        # AI polish: spelling/grammar cleanup through Groq llama (skip on failure).
        polished = polish(merged["text"])
        if polished:
            db.update_job(job_id, polished_text=polished, stage="Polished")

        # Charge credits only after a successful transcript (never for failures).
        if user_id:
            minutes = max(1.0, duration / 60.0)
            new_bal = accounts.deduct_minutes(user_id, minutes, f"job {job_id}")
            log.info("Deducted %.1f min from %s for job %s -> %.2f left",
                     minutes, user_id, job_id, new_bal)

        payload = {
            "final": {"text": merged["text"], "language": merged["language"],
                      "agreement": merged["agreement"], "segments": merged["segments"],
                      "speakers": merged.get("speakers")},
            "polished": polished,
            "models": [
                {"name": r.name, "label": r.label, "model": r.model, "text": r.text,
                 "language": r.language, "elapsed": round(r.elapsed, 1),
                 "agreement": merged["model_agreement"].get(r.name)}
                for r in results
            ],
            "failed": errors,
        }
        db.update_job(job_id, status="done", stage="Done", progress=1.0, language=merged["language"],
                      final_text=merged["text"], result_json=json.dumps(payload, ensure_ascii=False))
    except Exception as e:
        log.exception("Job %s failed", job_id)
        db.update_job(job_id, status="failed", stage="Failed", error=str(e)[:500])
    finally:
        shutil.rmtree(work, ignore_errors=True)
