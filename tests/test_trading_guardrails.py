"""Offline guardrail tests for the trading agent (no network)."""
import math
import os
import subprocess
import sys
import time
from pathlib import Path

TA = Path(__file__).resolve().parents[1] / "trading-agent"
sys.path.insert(0, str(TA))

os.environ["DATA_DIR"] = str(Path(__file__).resolve().parents[1] / "data" / "test_trading")

import ledger  # noqa: E402
from risk import RiskPolicy, round_trip_cost_frac, ts_day_start  # noqa: E402
from strategy import decide  # noqa: E402


def _candles(n=120, start=100.0, drift=0.2, seed=7):
    """Rising spot-ish series with a little noise (deterministic)."""
    import random
    rng = random.Random(seed)
    out, price = [], start
    t = 1600000000000
    for _ in range(n):
        o, h, l = price, price * 1.01, price * 0.99
        price = price * (1 + drift / 100) + rng.uniform(-0.5, 0.5)
        out.append({"time": t, "open": o, "high": h, "low": l, "close": price, "volume": 1.0})
        t += 3600_000
    return out


def test_strategy_needs_enough_history():
    few = _candles(60)
    assert decide(few, False, None)["action"] == "hold"
    assert "not enough" in decide(few, False, None)["reason"]


def test_strategy_buys_in_uptrend_breakout():
    candles = _candles(160, drift=0.4)   # strong sustained uptrend
    # light the \"near breakout\" trigger by appending a spike near the 24-bar high
    high = max(c["high"] for c in candles[-24:])
    spike = {**candles[-1], "close": high}
    candles.append(spike)
    out = decide(candles, False, None)
    assert out["action"] == "buy", out
    assert out["stop_price"] and out["stop_price"] < out.get("price", high)


def test_strategy_sells_on_trailing_stop():
    candles = _candles(160)
    stop = candles[-1]["close"] * 1.1   # stop far above price → must trigger sell
    out = decide(candles, True, stop)
    assert out["action"] == "sell", out


def test_risk_caps_and_cooldown():
    pol = RiskPolicy()
    now = time.time()
    ok, why = pol.allowed(now, 500.0, 500.0, 0, 0)
    assert ok, why
    blocked, why1 = pol.allowed(now, 500.0, 500.0, pol.max_trades_per_day, 0)
    assert not blocked and "cap" in why1
    blocked, why2 = pol.allowed(now, 500.0, 480.0, 1, 0)   # -4% overnight start? within limit check is vs day start equity
    # a -5% day halt triggers
    blocked, why3 = pol.allowed(now, 500.0, 474.0, 1, 0)
    assert not blocked and "loss" in why3
    # cooldown
    blocked, why4 = pol.allowed(now, 500.0, 500.0, 1, now - 10)
    assert not blocked and "cooldown" in why4


def test_position_size_respects_minimum_notional():
    pol = RiskPolicy()
    size = pol.position_size()
    assert 90 <= size <= 250  # tiny-capital tuning: never above the absolute cap


def test_round_trip_cost_makes_scalping_unprofitable():
    assert round_trip_cost_frac() > 0.013   # ~1.35%: buys+sells+TDS before tax


def test_ledger_buy_sell_with_fees_and_tds():
    sys.modules.get("ledger")
    ledger.DB = ledger.DB.with_name(f"test_{int(time.time())}.db")
    with ledger.conn() as c:
        f = ledger.record_open(c, time.time(), "BTCINR", 250.0, 100.0)
        assert math.isclose(f["fee"], 0.425, abs_tol=0.02)      # 0.17% of 250
        assert f["qty"] == pytest_approx((250 - f["fee"]) / 100.0)
        r = ledger.record_close(c, time.time(), "BTCINR", f["qty"], 110.0, 249.575)
        # 1% TDS on the sell consideration (ledger stores rounded to paise)
        assert math.isclose(r["tds"], r["gross"] * 0.01, abs_tol=0.01)
        assert math.isclose(r["gross"], f["qty"] * 110.0, abs_tol=0.01)   # paise-rounded
        assert math.isclose(r["pnl"], r["net"] - 249.575, abs_tol=0.02)
        # by construction (10% move), total round trip must be net positive
        assert r["pnl"] > 0


def pytest_approx(x):
    class _A:
        def __eq__(self, other): return math.isclose(x, other, rel_tol=1e-9)
        def __repr__(self): return repr(x)
    return _A()


if __name__ == "__main__":
    subprocess.run([sys.executable, "-m", "pytest", __file__, "-q"], cwd=str(TA.parent))
