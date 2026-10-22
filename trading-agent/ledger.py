"""Paper-trade ledger (SQLite): the truth for paper mode and for_logs/dashboards.

Records every simulated fill with fees and 1% TDS on sells, computes equity in
INR, and exposes daily stats the risk module reads back. A separate live mode
(evidence in README) should reconcile against exchange fill data, never this.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

DB = Path(__file__).resolve().parent / "paper.ledger.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS fills (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL,
  pair TEXT NOT NULL,
  side TEXT NOT NULL,             -- buy | sell
  notional_inr REAL NOT NULL,     -- gross INR value traded
  qty REAL NOT NULL,
  price REAL NOT NULL,
  fee_inr REAL NOT NULL,          -- exchange fees included in notional outflow
  tds_inr REAL NOT NULL,          -- 1% of sell consideration (194S)
  note TEXT
);
CREATE TABLE IF NOT EXISTS state (
  key TEXT PRIMARY KEY,
  value TEXT
);
"""

TAKER_FEE = 0.0017
TDS = 0.01


def conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    with c:
        c.executescript(SCHEMA)
    return c


def record_open(c, ts: float, pair: str, inr: float, price: float) -> dict:
    fee = round(inr * TAKER_FEE, 2)
    qty = (inr - fee) / price
    c.execute("INSERT INTO fills (ts,pair,side,notional_inr,qty,price,fee_inr,tds_inr,note) "
              "VALUES (?,?,?,?,?,?,?,?,?)", (ts, pair, "buy", inr, qty, price, fee, 0, "paper buy"))
    return {"qty": qty, "fee": fee}


def record_close(c, ts: float, pair: str, qty: float, price: float, buy_cost: float) -> dict:
    gross = round(qty * price, 2)
    fee = round(gross * TAKER_FEE, 2)
    tds = round(gross * TDS, 2)
    net = round(gross - fee - tds, 2)
    pnl = round(net - buy_cost, 2)
    c.execute("INSERT INTO fills (ts,pair,side,notional_inr,qty,price,fee_inr,tds_inr,note) "
              "VALUES (?,?,?,?,?,?,?,?,?)", (ts, pair, "sell", gross, qty, price, fee, tds, f"pnl {pnl}"))
    return {"gross": gross, "fee": fee, "tds": tds, "net": net, "pnl": pnl}


def get_state(c, key: str) -> str | None:
    row = c.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def set_state(c, key: str, value: str) -> None:
    c.execute("INSERT INTO state (key,value) VALUES (?,?) "
              "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def held_position(c) -> dict | None:
    row = c.execute("SELECT * FROM fills WHERE side='buy' ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return None
    # still open if no later sell
    later = c.execute("SELECT 1 FROM fills WHERE side='sell' AND id>?", (row["id"],)).fetchone()
    return None if later else dict(row)


def stats(c, ts: float) -> dict:
    """Risk inputs: trades today (UTC), realized P&L, last action timestamp."""
    day_start = ts_day_start(ts)
    rows = [dict(r) for r in c.execute("SELECT * FROM fills ORDER BY id")]
    buys_today = [r for r in rows if r["ts"] >= day_start and r["side"] == "buy"]
    realized = sum(float(r["note"].split()[-1]) for r in rows
                   if r["side"] == "sell" and r["note"].startswith("pnl"))
    last_trade_ts = rows[-1]["ts"] if rows else 0.0
    return {"fills": len(rows), "trades_today": len(buys_today),
            "realized_pnl": round(realized, 2), "last_trade_ts": last_trade_ts}


def ts_day_start(ts: float) -> float:
    from datetime import datetime, timezone
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc).timestamp()


if __name__ == "__main__":
    with conn() as c:
        print(c.execute("SELECT * FROM fills ORDER BY id DESC LIMIT 5").fetchall())
