"""Strategy: slow trend-following on 1-hour INR candles.

Rules (deliberately boring — high-frequency trading cannot clear India's
~1.35% round-trip fee/TDS cost on a ₹500 account):
- BUY when the fast EMA has been above the slow EMA for the last 3 closed
  candles AND price closes within one ATR of a 24-bar breakout high.
- HOLD with an ATR trailing stop (default 2.5×ATR) until it trips.
- The stop is evaluated on *closed* candles only: no flicker, no revenge trades.
- Cooldown + trade caps live in risk.py; this module stays pure.

Parameters are env-tunable via TRADE_* names below.
"""
from __future__ import annotations

import os

FAST = int(os.getenv("TRADE_EMA_FAST", "12"))
SLOW = int(os.getenv("TRADE_EMA_SLOW", "48"))
BREAKOUT_BARS = int(os.getenv("TRADE_BREAKOUT_BARS", "24"))
CONFIRM_BARS = int(os.getenv("TRADE_CONFIRM_BARS", "3"))
ATR_BARS = int(os.getenv("TRADE_ATR_BARS", "14"))
ATR_STOP_MULT = float(os.getenv("TRADE_ATR_STOP", "2.5"))


def _ema(vals: list[float], n: int) -> float | None:
    if len(vals) < n:
        return None
    k = 2 / (n + 1)
    e = sum(vals[:n]) / n
    for v in vals[n:]:
        e = v * k + e * (1 - k)
    return e


def indicators(candles: list[dict]) -> dict:
    closes = [c["close"] for c in candles]
    highs, lows = [c["high"] for c in candles], [c["low"] for c in candles]
    trs = [max(h - l, abs(h - p), abs(l - p))
           for h, l, p in zip(highs[1:], lows[1:], closes[1:])]
    return {"ema_fast": _ema(closes, FAST), "ema_slow": _ema(closes, SLOW),
            "atr": _ema(trs, ATR_BARS) if len(trs) >= ATR_BARS else None,
            "breakout_high": max(c["high"] for c in candles[-BREAKOUT_BARS:]) if len(candles) >= BREAKOUT_BARS else None,
            "last_close": closes[-1] if closes else None}


def decide(candles: list[dict], held: bool, stop_price: float | None) -> dict:
    """Return {action: buy|hold|sell, reason, stop_price} on CLOSED candles."""
    if len(candles) < SLOW + ATR_BARS + 2:
        return {"action": "hold", "reason": "not enough history yet"}
    ind = indicators(candles[:-1])   # exclude the live (open) candle
    px = candles[-1]["close"]
    atr = ind["atr"] or 0.0

    if held:
        if stop_price is not None and px <= stop_price:
            return {"action": "sell", "reason": f"trailing stop hit ({stop_price:.2f})", "stop_price": None}
        new_stop = max(stop_price or 0, px - ATR_STOP_MULT * atr) if atr else stop_price
        return {"action": "hold", "reason": "riding trend", "stop_price": new_stop}

    fast, slow = ind["ema_fast"], ind["ema_slow"]
    if not fast or not slow or fast <= slow:
        return {"action": "hold", "reason": "no uptrend", "stop_price": None}

    # uptrend confirmed for N consecutive closed candles
    closes = [c["close"] for c in candles[:-1]]
    k = 2 / (FAST + 1); e = sum(closes[:FAST]) / FAST
    series = []
    for v in closes[FAST:]:
        e = v * k + e * (1 - k)
        series.append(e)
    k2 = 2 / (SLOW + 1); e2 = sum(closes[:SLOW]) / SLOW
    series2 = []
    for v in closes[SLOW:]:
        e2 = v * k2 + e2 * (1 - k2)
        series2.append(e2)
    confirm = all(series[i] > series2[i] for i in range(-CONFIRM_BARS, 0)) \
        if len(series) >= CONFIRM_BARS and len(series2) >= CONFIRM_BARS else False
    if not confirm:
        return {"action": "hold", "reason": "uptrend too fresh", "stop_price": None}

    bh = ind["breakout_high"]
    if bh and px >= bh - atr:                       # near a breakout
        stop = px - ATR_STOP_MULT * atr
        return {"action": "buy", "reason": f"confirmed uptrend near breakout high {bh:.2f}",
                "stop_price": stop}
    return {"action": "hold", "reason": "trend not at breakout", "stop_price": None}
