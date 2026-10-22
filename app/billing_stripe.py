"""Stripe glue: hosted Checkout, return-page verification, webhook.

Works *alongside* Razorpay (same orders/_mark_paid plumbing in billing.py), so
one ledger credits each paid order exactly once, whichever gateway settles it.

Paths, both idempotent:
1. Return verification (works without webhooks, e.g. on localhost): the browser
   lands back on the site with ?session_id=...; we retrieve the Checkout
   Session server-side, confirm it is paid, matches this order/user, and then
   credit.
2. Webhook: checkout.session.completed (and async_payment_succeeded) with
   Stripe-style HMAC signature verification over the raw body via the SDK.
"""
from __future__ import annotations

import logging
import secrets
import time

import stripe

from . import accounts
from .config import settings
from .billing import bundle, _mark_paid

log = logging.getLogger(__name__)


def _plain(obj) -> dict:
    """Stripe SDK returns StripeObject wrappers in some paths and dicts in
    others; normalize to a plain dict (StripeObject blocks .get())."""
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    return dict(obj or {})


def available() -> bool:
    return bool(settings.stripe_secret_key)


def create_session(user_id: str, bundle_name: str, base_url: str) -> dict:
    """Create a local order + Stripe Checkout Session. Returns the redirect URL."""
    if not available():
        raise RuntimeError("Stripe keys are not configured (.env)")
    if not base_url.startswith(("http://", "https://")):
        raise ValueError("Bad base url")
    b = bundle(bundle_name)
    if not b:
        raise ValueError("Unknown bundle")
    order_id = "lo_" + secrets.token_hex(8)
    with accounts._conn() as c:
        c.execute("INSERT INTO orders (id, user_id, minutes, amount, status, created_at) "
                  "VALUES (?,?,?,?,?,?)",
                  (order_id, user_id, b["minutes"], b["amount_paise"], "created", time.time()))
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{
            "quantity": 1,
            "price_data": {
                "currency": "inr",
                "unit_amount": b["amount_paise"],
                "product_data": {
                    "name": f"CallTranscript — {b['label']}",
                    "description": "Prepaid transcription credits (1 minute = 1 credit)",
                },
            },
        }],
        success_url=(f"{base_url}#stripe-paid&order={order_id}"
                     "&session_id={CHECKOUT_SESSION_ID}"),
        cancel_url=f"{base_url}#pricing",
        metadata={"local_order": order_id, "user_id": user_id, "bundle": bundle_name},
    )
    return {"order": order_id, "url": session.url}


def verify_return(user_id: str, order_id: str, session_id: str) -> dict:
    """Path 1: the browser returned from Checkout with its session id."""
    with accounts._conn() as c:
        row = c.execute("SELECT user_id, status FROM orders WHERE id=?", (order_id,)).fetchone()
    if not row:
        raise ValueError("Unknown order")
    if row["status"] == "paid":
        return {"credited": False, "already_paid": True, "balance": accounts.balance(row["user_id"])}
    if row["user_id"] != user_id:
        raise ValueError("This order belongs to a different account")
    session = _plain(stripe.checkout.Session.retrieve(session_id or ""))
    if (session.get("metadata") or {}).get("local_order") != order_id:
        raise ValueError("Payment session does not match this order")
    if (session.get("metadata") or {}).get("user_id") != user_id:
        raise ValueError("Payment session does not belong to this account")
    if session.get("payment_status") != "paid":
        raise ValueError("Payment is not completed yet")
    return _mark_paid(order_id)


def handle_webhook(raw_body: bytes, signature: str) -> dict:
    """Path 2: checkout.session.completed webhook with signature verification."""
    if not settings.stripe_webhook_secret:
        raise RuntimeError("STRIPE_WEBHOOK_SECRET not configured")
    try:
        event = stripe.Webhook.construct_event(raw_body, signature or "",
                                               settings.stripe_webhook_secret)
    except Exception as e:
        raise ValueError(f"Webhook signature verification failed ({type(e).__name__})")
    if event.type in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        sess = _plain(event.data.object)
        local_order = (sess.get("metadata") or {}).get("local_order")
        if local_order and sess.get("payment_status") == "paid":
            try:
                _mark_paid(local_order)
            except ValueError:
                return {"ok": False, "reason": "unknown order"}
    return {"ok": True}
