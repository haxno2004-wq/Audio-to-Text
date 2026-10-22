"""Trading agent loop — PAPER MODE BY DEFAULT.

Usage:
  .\\.venv\\Scripts\\python.exe trading-agent\\bot.py              # one decision cycle
  .\\.venv\\Scripts\\python.exe trading-agent\\bot.py --loop       # every POLL_MINUTES
  LIVE_MODE=1 + COINDCX_API_KEY/SECRET in env → real orders (explicit opt-in)

Per cycle on TRADE_PAIR (default BTCINR, 1-hour candles):
1. Pull candles from the public API, run strategy.decide on CLOSED candles.
2. Risk gate: sizing, trade caps, cooldown, daily-loss halt (risk.py).
3. Paper mode: execute into the SQLite ledger at the live last price.
   Live mode: submit via the signed CoinDCX endpoint and verify the fill.
4. Print one JSON decision line. The paper DB is the audit trail.

Nothing here is investment advice and there is no guaranteed edge: run
backtest.py, then paper days, before even thinking about LIVE_MODE.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

from coindcx import CoinDCX
from strategy import decide
from risk import RiskPolicy, ts_day_start
import ledger

PAIR = os.getenv("TRADE_PAIR", "BTCINR")
POLL_MINUTES = int(os.getenv("POLL_MINUTES", "15"))
LIVE = os.getenv("LIVE_MODE", "0") == "1"


def cycle(ex: CoinDCX, pol: RiskPolicy) -> dict:
    now = time.time()
    candles = ex.candles(PAIR, "1h", 200)

    with ledger.conn() as c:
        held = ledger.held_position(c)
        st = ledger.stats(c, now)
        stop = float(ledger.get_state(c, "stop_price") or 0) or None
        sig = decide(candles, held is not None, stop)
        equity = pol.capital + st["realized_pnl"]
        can, why = pol.allowed(now, equity, equity,
                               st["trades_today"], st["last_trade_ts"])
        out = {"ts": int(now), "price": candles[-1]["close"], "signal": sig["action"],
               "reason": sig.get("reason", ""), "risk": why, "executed": None,
               "equity": round(pol.capital + st["realized_pnl"], 2)}

        if sig["action"] == "buy" and not held and can:
            size = pol.position_size()
            if size < pol.min_notional:
                out["reason"] = f"skipped: {size} below pair minimum {pol.min_notional}"
            else:
                out["executed"] = (ex.create_market_order(PAIR, "buy", size)
                                   if LIVE else
                                   {"paper": True, **ledger.record_open(c, now, PAIR, size, candles[-1]["close"]),
                                    "stop": sig.get("stop_price")})
                if isinstance(out["executed"], dict) and out["executed"].get("stop"):
                    ledger.set_state(c, "stop_price", str(out["executed"]["stop"]))
                elif LIVE:
                    ledger.set_state(c, "stop_price", str(sig.get("stop_price") or 0))

        elif sig["action"] == "sell" and held and can:
            buy_cost = held["notional_inr"] - held["fee_inr"]
            out["executed"] = (ex.create_market_order(PAIR, "sell", held["qty"])
                               if LIVE else
                               {"paper": True, **ledger.record_close(c, now, PAIR,
                                                                     held["qty"], candles[-1]["close"], buy_cost)})
            ledger.set_state(c, "stop_price", "")

        elif sig["action"] == "hold" and held is not None and sig.get("stop_price"):
            ledger.set_state(c, "stop_price", str(sig["stop_price"]))

        out["stop_price"] = ledger.get_state(c, "stop_price") or None
        return out


def report_day_summary() -> str:
    with ledger.conn() as c:
        st = ledger.stats(c, time.time())
    return f"fills={st['fills']} realized₹{st['realized_pnl']}"


def main() -> None:
    try:   # Windows consoles are cp1252 by default; ₹ and JSON dumps need UTF-8
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", action="store_true", help="run forever every POLL_MINUTES")
    args = ap.parse_args()
    ex = CoinDCX(os.getenv("COINDCX_API_KEY", ""), os.getenv("COINDCX_API_SECRET", ""))
    pol = RiskPolicy()
    print(f"trading-agent {'LIVE' if LIVE else 'PAPER'} pair={PAIR} "
          f"capital=₹{pol.capital} poll={POLL_MINUTES}m", flush=True)
    while True:
        try:
            print(json.dumps(cycle(ex, pol), default=str), flush=True)
        except Exception as e:
            print("cycle error:", type(e).__name__, str(e)[:200], flush=True)
        if not args.loop:
            break
        time.sleep(POLL_MINUTES * 60)


if __name__ == "__main__":
    sys.exit(main())
