"""Backtest strategy.py on REAL CoinDCX historical candles (public API).

Courage test before paper/live mode: does the slow trend design survive after
fees (2×0.17%) and 1% TDS? Windows and params are env-overridable.

  .\\.venv\\Scripts\\python.exe trading-agent\\backtest.py [pair=BTCINR] [bars=1000]

Output: trades, win rate, total return, max drawdown, per-trade table (last 10),
and an explicit note that past performance does not imply future results.
"""
from __future__ import annotations

import os
import sys

import httpx

from coindcx import CoinDCX, DEFAULT_FEES
from strategy import decide, indicators
from risk import round_trip_cost_frac

TAKER = DEFAULT_FEES["taker"]
TDS = DEFAULT_FEES["tds_on_sell"]


def backtest(pair: str = "BTCINR", bars: int = 1000, interval: str = "1h",
             capital: float = 500.0, pos_frac: float = 0.5) -> dict:
    ex = CoinDCX()
    candles = ex.candles(pair, interval, min(bars, 1000))
    if len(candles) < 200:
        return {"error": f"only got {len(candles)} candles from the API"}

    cash, pos, entry_cost, stop, equity_peak = capital, 0.0, 0.0, 0.0, capital
    trades = []
    history = []
    for i in range(200, len(candles) - 1):
        window = candles[max(0, i - 200):i + 1]
        sig = decide(window, pos > 0, stop)
        px = window[-1]["close"]
        if sig["action"] == "buy" and cash >= capital * (1 - pos_frac) and cash > 100:
            inr = min(cash, capital * pos_frac)
            fee = inr * TAKER
            pos, entry_cost = (inr - fee) / px, inr
            cash -= inr
            stop = sig.get("stop_price") or 0.0
        elif pos > 0 and (sig["action"] == "sell" or px <= stop):
            gross = pos * px
            net = gross * (1 - TAKER - TDS)
            cash += net
            trades.append(net - entry_cost if entry_cost else 0.0)
            pos, entry_cost, stop = 0.0, 0.0, 0.0
        eq = cash + pos * px
        equity_peak = max(equity_peak, eq)
        history.append(eq)

    if pos > 0:                      # mark to last close, trade not closed
        px = candles[-1]["close"]
        net = pos * px * (1 - TAKER - TDS)
        realized_open = net - entry_cost if entry_cost else 0.0
    else:
        realized_open = 0.0

    eq = history[-1] if history else capital
    closed = [t for t in trades if t != 0.0] or trades
    wins = sum(1 for t in closed if t > 0)
    return {
        "pair": pair, "candles": len(candles), "interval": interval,
        "capital": capital, "final_equity": round(eq, 2),
        "total_return_pct": round((eq - capital) / capital * 100, 2),
        "max_drawdown_pct": round((equity_peak - min(history or [capital])) / equity_peak * 100, 2),
        "closed_trades": len(closed), "win_rate_pct": round(wins / len(closed) * 100, 0) if closed else 0,
        "round_trip_cost_pct": round(round_trip_cost_frac() * 100, 2),
        "open_position_marked": round(realized_open, 2) if pos > 0 else None,
        "note": "Past performance does not imply future results; run paper mode weeks before live.",
    }


if __name__ == "__main__":
    pair = sys.argv[1] if len(sys.argv) > 1 else os.getenv("TRADE_PAIR", "BTCINR")
    bars = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
    import json
    print(json.dumps(backtest(pair, bars), indent=2))
