"""CoinDCX REST client (paper-mode friendly).

Public endpoints need no auth; trading endpoints authenticate exactly as the
official docs (https://docs.coindcx.com) specify: HMAC-SHA256 of the JSON body
with the API secret, key in X-AUTH-APIKEY, signature in X-AUTH-SIGNATURE.

Only SPOT is used. No withdrawal permissions are ever requested: create your
API key with trade-only rights (and IP whitelisting; the bot asserts the key
is the same machine's IP in live mode).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time

import httpx

BASE = "https://api.coindcx.com"
# Fees: verify your actual tier in the dashboard (volume-based). Default below
# is the common entry spot tier; TDS is 1% of the SELL consideration (194S).
DEFAULT_FEES = {"maker": 0.0017, "taker": 0.0017, "tds_on_sell": 0.01}


def server_time(client: httpx.Client) -> int:
    """Server epoch seconds (clock-skew-safe timestamps for signed posts)."""
    r = client.get(f"{BASE}/exchange/v1/time")
    r.raise_for_status()
    js = r.json()
    return int((js.get("ISO") if "ISO" in js else js.get("time", 0)) if isinstance(js, dict) else js)


class CoinDCX:
    def __init__(self, api_key: str = "", secret: str = ""):
        self.key, self.secret = api_key, secret
        self.http = httpx.Client(timeout=30)

    # ---------------------------------------------------------------- public

    def candles(self, pair: str = "BTCINR", interval: str = "1h", limit: int = 200) -> list[dict]:
        """Historic OHLC rows: {time(ms), open, high, low, close, volume} ascending.
        Plain names (BTCINR) are mapped to the API's prefixed form (B-BTC_INR)."""
        api_pair = pair if "_" in pair else ("B-" + pair[:-3] + "_" + pair[-3:])
        r = self.http.get(f"{BASE}/market_data/candles",
                          params={"pair": api_pair, "interval": interval, "limit": limit})
        r.raise_for_status()
        js = r.json()
        rows = js.get("data") if isinstance(js, dict) else js
        out = []
        for w in rows:
            if not isinstance(w, dict):
                continue
            t = w.get("time", w.get("t"))
            out.append({"time": int(t), "open": float(w.get("open", w.get("o"))),
                        "high": float(w.get("high", w.get("h"))),
                        "low": float(w.get("low", w.get("l"))),
                        "close": float(w.get("close", w.get("c"))),
                        "volume": float(w.get("volume", w.get("v", 0)))})
        out.sort(key=lambda x: x["time"])
        return out

    def markets_details(self) -> list[dict]:
        r = self.http.get(f"{BASE}/exchange/v1/markets_details")
        r.raise_for_status()
        return r.json()

    def market_meta(self, pair: str) -> dict | None:
        """{min_quantity, min_notional, precision, step} for a pair like BTCINR.
        markets_details uses pair='I-BTC_INR' + a separate coindcx_name — match both."""
        api_pair = pair if "_" in pair else ("I-" + pair[:-3] + "_" + pair[-3:])
        for m in self.markets_details():
            if m.get("pair") == api_pair or m.get("coindcx_name") == pair:
                return m
        return None

    # ---------------------------------------------------------------- private

    def _signed_post(self, path: str, body: dict) -> dict:
        if not self.key or not self.secret:
            raise RuntimeError("COINDCX_API_KEY / COINDCX_API_SECRET not configured")
        body = {**body, "timestamp": server_time(self.http)}
        payload = json.dumps(body)
        sig = hmac.new(self.secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        r = self.http.post(f"{BASE}{path}", content=payload,
                           headers={"X-AUTH-APIKEY": self.key,
                                    "X-AUTH-SIGNATURE": sig,
                                    "Content-Type": "application/json"})
        if r.status_code >= 300:
            raise RuntimeError(f"CoinDCX API error {r.status_code}: {r.text[:300]}")
        return r.json()

    def balances(self) -> list[dict]:
        out = self._signed_post("/exchange/v1/users/balances", {})
        if isinstance(out, dict):
            out = out.get("data", [out])
        return [b for b in out if isinstance(b, dict)]

    def inr_available(self) -> float:
        for b in self.balances():
            if str(b.get("asset", "")).upper() == "INR":
                return float(b.get("balance", 0))
        return 0.0

    def create_market_order(self, pair: str, side: str, notional_inr: float) -> dict:
        """Market order sized by INR notional. spot only; side: buy|sell."""
        order_type = "market_order"
        body = {"side": side.lower(), "exchange": pair, "order_type": order_type}
        if side.lower() == "buy":
            body["total_amount"] = round(notional_inr, 2)     # INR to spend
        else:
            # selling by INR notional uses price_quantity_type negligible;
            # CoinDCX sell market orders take quantity of the base asset, so the
            # caller resolves qty upstream via prices + balances.
            body["total_quantity"] = round(notional_inr, 8)
        return self._signed_post("/exchange/v1/orders/create", body)
