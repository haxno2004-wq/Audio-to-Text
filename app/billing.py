"""Razorpay glue: order creation, checkout signature verification, webhook.

Uses plain HTTP via httpx (no extra SDK dependency).

Two credit paths, both idempotent (an order is credited at most once):
1. Checkout handler (works even without a webhook, e.g. on localhost):
   the browser returns razorpay_order_id, razorpay_payment_id and
   razorpay_signature; we verify HMAC-SHA256(order_id|payment_id) against the
   key secret before crediting.
2. Webhook (production-grade): a "payment.captured" event whose notes carry
   local_order; HMAC-SHA256 of the raw body against RAZORPAY_WEBHOOK_SECRET.
   Whichever path arrives first marks the order paid; the other becomes a no-op.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time

import httpx

from . import accounts
from .config import settings

log = logging.getLogger(__name__)
_ORDERS_URL = "https://api.razorpay.com/v1/orders"


def bundle(name: str) -> dict | None:
    return next((b for b in settings.credit_bundles if b["name"] == name), None)


def bundles() -> list[dict]:
    """Public shape for the pricing page (hides nothing, but tidies)."""
    return settings.credit_bundles


def create_order(user_id: str, bundle_name: str) -> dict:
    """Create a local order + Razorpay order. Returns what Checkout.js needs."""
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise RuntimeError("Razorpay keys are not configured (.env)")
    b = bundle(bundle_name)
    if not b:
        raise ValueError("Unknown bundle")
    order_id = "lo_" + secrets.token_hex(8)
    with accounts._conn() as c:
        c.execute("INSERT INTO orders (id, user_id, minutes, amount, status, created_at) "
                  "VALUES (?,?,?,?,?,?)",
                  (order_id, user_id, b["minutes"], b["amount_paise"], "created", time.time()))
    body = {
        "amount": b["amount_paise"],
        "currency": "INR",
        "receipt": order_id,
        "notes": {"local_order": order_id, "user_id": user_id, "bundle": bundle_name},
    }
    r = httpx.post(_ORDERS_URL, json=body, timeout=30,
                   auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
    if r.status_code >= 300:
        log.error("Razorpay order failed: %s %s", r.status_code, r.text[:300])
        raise RuntimeError("Payment gateway rejected the order")
    rz = r.json()
    return {"order": order_id, "razorpay_order_id": rz["id"], "amount": b["amount_paise"],
            "key_id": settings.razorpay_key_id, "bundle": bundle_name,
            "minutes": b["minutes"], "currency": "INR"}


# ------------------------------------------------------------------ verify

def _checkout_sign(order_id: str, payment_id: str) -> str:
    return hmac.new(settings.razorpay_key_secret.encode(),
                    f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()


def verify_checkout(local_order: str, razorpay_order_id: str, payment_id: str,
                    signature: str) -> dict:
    """Path 1: signature from the browser checkout handler. Credits the account."""
    with accounts._conn() as c:
        row = c.execute("SELECT user_id, minutes, status FROM orders WHERE id=?",
                        (local_order,)).fetchone()
    if not row:
        raise ValueError("Unknown order")
    if row["status"] == "paid":
        return {"credited": False, "already_paid": True,
                "balance": accounts.balance(row["user_id"])}
    expected = _checkout_sign(razorpay_order_id, payment_id)
    if not hmac.compare_digest(expected, signature or ""):
        raise ValueError("Payment signature verification failed")
    return _mark_paid(local_order)


def _mark_paid(local_order: str) -> dict:
    """Flip order -> paid and credit minutes exactly once."""
    with accounts._conn() as c:
        row = c.execute("SELECT user_id, minutes, status FROM orders WHERE id=?",
                        (local_order,)).fetchone()
        if not row:
            raise ValueError("Unknown order")
        first = row["status"] != "paid"
        if first:
            c.execute("UPDATE orders SET status='paid' WHERE id=?", (local_order,))
    if not first:
        return {"credited": False, "already_paid": True,
                "balance": accounts.balance(row["user_id"])}
    bal = accounts.add_minutes(row["user_id"], row["minutes"], "topup", f"order {local_order}")
    log.info("Credited %s min to user %s (order %s)", row["minutes"], row["user_id"], local_order)
    return {"credited": True, "already_paid": False, "balance": bal}


def handle_webhook(raw_body: bytes, signature: str) -> dict:
    """Path 2: Razorpay webhook. Credits only after payload signature passes."""
    if not settings.razorpay_webhook_secret:
        raise RuntimeError("RAZORPAY_WEBHOOK_SECRET not configured")
    expected = hmac.new(settings.razorpay_webhook_secret.encode(), raw_body,
                        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature or ""):
        raise ValueError("Webhook signature verification failed")
    event = json.loads(raw_body.decode("utf-8", "replace"))
    payment = (event.get("payload", {}).get("payment", {}) or {}).get("entity", {}) or {}
    local_order = (payment.get("notes", {}) or {}).get("local_order")
    if not local_order:
        return {"ok": True, "reason": "no local order in payment notes"}
    try:
        _mark_paid(local_order)
        return {"ok": True}
    except ValueError:
        return {"ok": False, "reason": "unknown order"}


def resolve_user_from_header(authorization: str) -> dict | None:
    if not authorization:
        return None
    token = authorization.removeprefix("Bearer ").strip()
    return accounts.user_for_token(token)
