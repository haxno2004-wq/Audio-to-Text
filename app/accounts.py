"""User accounts with prepaid transcription credits (SQLite-backed).

Design:
- Sign up/in with email + password (PBKDF2-SHA256, 200k iterations, salted).
- Each user gets a credits row; credits are MINUTES of audio.
- Ledger rows record every topup (Razorpay) and every deduction (transcription).
- The worker deducts ONLY after a successful transcript, so a failed job never
  costs the user anything.
- Anonymous use is still allowed when BILLING_ENABLED=0 (local/dev/your own use).
"""
from __future__ import annotations

import hashlib
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from typing import Iterator

from .config import settings

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PBKDF2_ITERS = 200_000
SESSION_TTL = 30 * 24 * 3600.0   # 30 days

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id           TEXT PRIMARY KEY,
  email        TEXT UNIQUE NOT NULL,
  pw_hash      TEXT NOT NULL,
  plan         TEXT NOT NULL DEFAULT 'free',
  created_at   REAL NOT NULL,
  updated_at   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS credits (
  user_id      TEXT PRIMARY KEY REFERENCES users(id),
  balance      REAL NOT NULL DEFAULT 0     -- minutes
);
CREATE TABLE IF NOT EXISTS ledger (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id      TEXT NOT NULL REFERENCES users(id),
  kind         TEXT NOT NULL,              -- topup | use | grant
  minutes      REAL NOT NULL,              -- positive for topup/grant, negative for use
  note         TEXT,
  created_at   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
  id           TEXT PRIMARY KEY,
  user_id      TEXT NOT NULL REFERENCES users(id),
  minutes      REAL NOT NULL,
  amount       INTEGER NOT NULL,           -- paise (INR minor units)
  status       TEXT NOT NULL DEFAULT 'created',  -- created | paid | failed
  created_at   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  token        TEXT PRIMARY KEY,
  user_id      TEXT NOT NULL REFERENCES users(id),
  created_at   REAL NOT NULL,
  expires_at   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS reward_claims (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id      TEXT NOT NULL REFERENCES users(id),
  ip           TEXT NOT NULL DEFAULT '',
  minutes      REAL NOT NULL,
  created_at   REAL NOT NULL
);
"""


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(settings.data_dir / "app.db", timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=30000")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def enabled() -> bool:
    """Billing is opt-in: off by default so local/self-hosted use stays open."""
    return getattr(settings, "billing_enabled", False)


# ------------------------------------------------------------------ passwords

def _hash_pw(pw: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), PBKDF2_ITERS)
    return f"{salt}${dk.hex()}"


def _check_pw(pw: str, stored: str) -> bool:
    try:
        salt, hexdk = stored.split("$", 1)
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), PBKDF2_ITERS)
        return secrets.compare_digest(dk.hex(), hexdk)
    except (ValueError, AttributeError):
        return False


# ------------------------------------------------------------------ accounts

def init_db() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    with _conn() as c:
        c.executescript(SCHEMA)


def signup(email: str, pw: str) -> dict:
    """Create an account. New users get the free-tier grant from .env."""
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        raise ValueError("Enter a valid email address")
    if len(pw) < 8:
        raise ValueError("Password must be at least 8 characters")
    uid = secrets.token_hex(8)
    now = time.time()
    grant = getattr(settings, "free_minutes", 30.0)
    with _conn() as c:
        if c.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            raise ValueError("This email is already registered — try signing in")
        c.execute("INSERT INTO users (id, email, pw_hash, plan, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                  (uid, email, _hash_pw(pw), "free", now, now))
        c.execute("INSERT INTO credits (user_id, balance) VALUES (?,?)", (uid, grant))
        c.execute("INSERT INTO ledger (user_id, kind, minutes, note, created_at) VALUES (?,?,?,?,?)",
                  (uid, "grant", grant, "free tier", now))
    return {"id": uid, "email": email, "balance": grant}


def login(email: str, pw: str, via: str = "") -> str:
    """Return a session token, or raise ValueError('bad credentials')."""
    email = email.strip().lower()
    with _conn() as c:
        row = c.execute("SELECT id, pw_hash FROM users WHERE email=?", (email,)).fetchone()
        if not row or not _check_pw(pw, row["pw_hash"]):
            raise ValueError("Wrong email or password")
        token = secrets.token_urlsafe(32)
        now = time.time()
        c.execute("INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?,?,?,?)",
                  (token, row["id"], now, now + SESSION_TTL))
    return token


def logout(token: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM sessions WHERE token=?", (token,))


def user_for_token(token: str) -> dict | None:
    """Resolve a session token -> {id, email, plan, balance} or None."""
    if not token:
        return None
    with _conn() as c:
        row = c.execute(
            "SELECT u.id, u.email, u.plan FROM sessions s JOIN users u ON u.id=s.user_id "
            "WHERE s.token=? AND s.expires_at > ?", (token, time.time())).fetchone()
        if not row:
            return None
        bal = c.execute("SELECT balance FROM credits WHERE user_id=?", (row["id"],)).fetchone()
    return {"id": row["id"], "email": row["email"], "plan": row["plan"],
            "balance": round(bal["balance"], 2) if bal else 0.0}


def balance(user_id: str) -> float:
    with _conn() as c:
        row = c.execute("SELECT balance FROM credits WHERE user_id=?", (user_id,)).fetchone()
    return row["balance"] if row else 0.0


def ledger(user_id: str, limit: int = 50) -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT kind, minutes, note, created_at FROM ledger "
                         "WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit)).fetchall()
    return [dict(r) for r in rows]


# ------------------------------------------------------------------ credits

def add_minutes(user_id: str, minutes: float, kind: str, note: str) -> float:
    with _conn() as c:
        row = c.execute("SELECT balance FROM credits WHERE user_id=?", (user_id,)).fetchone()
        new_bal = round((row["balance"] if row else 0.0) + minutes, 2)
        if row:
            c.execute("UPDATE credits SET balance=? WHERE user_id=?", (new_bal, user_id))
        else:
            c.execute("INSERT INTO credits (user_id, balance) VALUES (?,?)", (user_id, new_bal))
        c.execute("INSERT INTO ledger (user_id, kind, minutes, note, created_at) VALUES (?,?,?,?,?)",
                  (user_id, kind, round(minutes, 2), note, time.time()))
    return new_bal


# ------------------------------------------------------------------ rewards

def _utc_day_start() -> float:
    return time.time() - (time.time() % 86400)


def rewards_used_today(user_id: str, ip: str = "") -> tuple[int, int]:
    """(claims_by_this_user_today, claims_from_this_ip_today) since UTC midnight."""
    day = _utc_day_start()
    with _conn() as c:
        n_user = c.execute("SELECT COUNT(*) AS n FROM reward_claims "
                           "WHERE user_id=? AND created_at>=?", (user_id, day)).fetchone()["n"]
        n_ip = 0
        if ip:
            n_ip = c.execute("SELECT COUNT(*) AS n FROM reward_claims "
                             "WHERE ip=? AND created_at>=?", (ip, day)).fetchone()["n"]
    return n_user, n_ip


def claim_reward(user_id: str, ip: str, minutes: float, daily_cap: int) -> dict:
    """Credit free minutes for a rewarded-ad view. Enforces cap and records it.

    Raises ValueError('reward limit reached') when the account (or the IP it
    comes from) has already claimed today's cap.
    """
    if minutes <= 0 or daily_cap <= 0:
        raise ValueError("Rewards are disabled")
    n_user, n_ip = rewards_used_today(user_id, ip)
    if n_user >= daily_cap or n_ip >= daily_cap * 3:   # IP cap is looser: shared offices/NAT
        raise ValueError("Daily reward limit reached — come back tomorrow")
    with _conn() as c:
        c.execute("INSERT INTO reward_claims (user_id, ip, minutes, created_at) VALUES (?,?,?,?)",
                  (user_id, ip or "", minutes, time.time()))
    bal = add_minutes(user_id, minutes, "reward", "watched ad")
    return {"credited": minutes, "balance": bal,
            "remaining": daily_cap - n_user - 1}


def deduct_minutes(user_id: str, minutes: float, note: str) -> float:
    """Charge credits after a successful transcription. Floors at 0."""
    minutes = max(0.0, round(minutes, 2))
    with _conn() as c:
        row = c.execute("SELECT balance FROM credits WHERE user_id=?", (user_id,)).fetchone()
        new_bal = round(max(0.0, (row["balance"] if row else 0.0) - minutes), 2)
        if row:
            c.execute("UPDATE credits SET balance=? WHERE user_id=?", (new_bal, user_id))
        else:
            c.execute("INSERT INTO credits (user_id, balance) VALUES (?,?)", (user_id, new_bal))
        c.execute("INSERT INTO ledger (user_id, kind, minutes, note, created_at) VALUES (?,?,?,?,?)",
                  (user_id, "use", -minutes, note, time.time()))
    return new_bal
