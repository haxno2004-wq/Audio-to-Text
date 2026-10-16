"""SQLite job store. WAL mode lets the API and the worker share one file."""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id            TEXT PRIMARY KEY,
  filename      TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'queued',   -- queued | processing | done | failed
  stage         TEXT NOT NULL DEFAULT 'Queued',
  progress      REAL NOT NULL DEFAULT 0,
  language_hint TEXT,
  language      TEXT,
  duration      REAL,
  final_text    TEXT,
  result_json   TEXT,
  error         TEXT,
  created_at    REAL NOT NULL,
  updated_at    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);
"""

_UPDATABLE = {"status", "stage", "progress", "language", "duration", "final_text", "result_json", "polished_text", "error"}


@contextmanager
def conn():
    c = sqlite3.connect(settings.data_dir / "app.db", timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=30000")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    with conn() as c:
        c.executescript(SCHEMA)
        # lightweight migration for DBs created before the polish column existed
        cols = {r[1] for r in c.execute("PRAGMA table_info(jobs)").fetchall()}
        if "polished_text" not in cols:
            c.execute("ALTER TABLE jobs ADD COLUMN polished_text TEXT")


def create_job(job_id: str, filename: str, language_hint: str | None) -> None:
    now = time.time()
    with conn() as c:
        c.execute(
            "INSERT INTO jobs (id, filename, language_hint, created_at, updated_at) VALUES (?,?,?,?,?)",
            (job_id, filename, language_hint, now, now),
        )


def update_job(job_id: str, **fields) -> None:
    bad = set(fields) - _UPDATABLE
    if bad:
        raise ValueError(f"Unknown job fields: {bad}")
    fields["updated_at"] = time.time()
    sets = ", ".join(f"{k}=?" for k in fields)
    with conn() as c:
        c.execute(f"UPDATE jobs SET {sets} WHERE id=?", (*fields.values(), job_id))


def get_job(job_id: str) -> dict | None:
    with conn() as c:
        row = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        return None
    job = dict(row)
    raw = job.pop("result_json", None)
    job["result"] = json.loads(raw) if raw else None
    return job


def list_jobs(limit: int = 100) -> list[dict]:
    with conn() as c:
        rows = c.execute(
            "SELECT id, filename, status, duration, language, created_at FROM jobs "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_job(job_id: str) -> None:
    with conn() as c:
        c.execute("DELETE FROM jobs WHERE id=?", (job_id,))


def delete_all_jobs(skip_running: bool = True) -> list[str]:
    """Clear history. Running/queued jobs are skipped unless avoid that is impossible."""
    with conn() as c:
        if skip_running:
            rows = c.execute(
                "SELECT id FROM jobs WHERE status NOT IN ('queued','processing')"
            ).fetchall()
        else:
            rows = c.execute("SELECT id FROM jobs").fetchall()
        ids = [r["id"] for r in rows]
        if skip_running:
            c.execute("DELETE FROM jobs WHERE id IN (%s)" % ",".join("?" * len(ids)), ids) if ids else None
        else:
            c.execute("DELETE FROM jobs")
    return ids


def reset_unfinished() -> list[str]:
    """After a restart, jobs that were queued or mid-run go back to the start of the line."""
    with conn() as c:
        rows = c.execute(
            "SELECT id FROM jobs WHERE status IN ('queued','processing') ORDER BY created_at"
        ).fetchall()
        c.execute(
            "UPDATE jobs SET status='queued', stage='Queued', progress=0 "
            "WHERE status IN ('queued','processing')"
        )
    return [r["id"] for r in rows]
