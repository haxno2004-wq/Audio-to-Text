"""Risk guardrails, tuned for a ₹500 pilot on INR spot.

With two ~0.17% fills plus 1% TDS on the sell consideration, a round trip
costs ~1.35% of the money moved *before* tax — so the strategy must only
fire on signals that historically clear that hurdle, and position sizing is
conservative. No bot can promise profit; these caps keep the worst day small.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _f(name: str, d: float) -> float:
    return float(os.getenv(name, str(d)))


@dataclass
class RiskPolicy:
    capital: float = _f("TRADING_CAPITAL", 500.0)          # INR you are risking
    max_position_frac: float = _f("MAX_POSITION_FRAC", 0.5)  # ≤50% of capital in one position
    max_inr_position: float = _f("MAX_INR_POSITION", 250.0)  # absolute rupee cap too
    daily_max_loss_frac: float = _f("DAILY_MAX_LOSS_FRAC", 0.05)  # -5% of day's start = stop
    max_trades_per_day: int = int(os.getenv("MAX_TRADES_PER_DAY", "3"))
    cooldown_minutes: int = int(os.getenv("COOLDOWN_MINUTES", "240"))
    min_notional: float = _f("MIN_NOTIONAL", 100.0)         # exchange/pair minimums

    def position_size(self) -> float:
        return round(min(self.capital * self.max_position_frac, self.max_inr_position,
                         max(self.capital - 50, self.min_notional)), 2)

    def allowed(self, ts: float, day_start_equity: float, equity: float,
                trades_today: int, last_trade_ts: float) -> tuple[bool, str]:
        now = datetime.fromtimestamp(ts, tz=timezone.utc).date()
        if trades_today >= self.max_trades_per_day:
            return False, f"daily trade cap reached ({trades_today} today)"
        if ts - last_trade_ts < self.cooldown_minutes * 60:
            return False, "cooldown active"
        if day_start_equity and equity < day_start_equity * (1 - self.daily_max_loss_frac):
            return False, "daily loss limit hit — trading halted for today"
        return True, "ok"


def round_trip_cost_frac(*, taker: float = 0.0017, tds: float = 0.01) -> float:
    """Approx cost of buy+sell as a fraction of notional (before 30% VDA tax)."""
    return 2 * taker + tds          # ≈ 1.34%


MIN_EDGE_NEEDED = round_trip_cost_frac() + 0.01   # must beat fees by ≥1%


def ts_day_start(ts: float) -> float:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    day = datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc)
    return day.timestamp()
