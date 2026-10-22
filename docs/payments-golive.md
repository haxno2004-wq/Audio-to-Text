# Payment-gateway go-live checklist (Stripe + Razorpay)

Both gateways already run in the app. Toggle which one is live purely by which
keys you set — a gateway without keys simply doesn't appear on the pricing page.

## Stripe (second gateway)

1. **Get test keys** — console.stripe.com → Developers → API keys (use a
   *test* key first): `sk_test_...`
2. **Create the webhook** — Developers → Webhooks → Add endpoint:
   - URL: `https://your-site/api/billing/stripe/webhook`
   - Events: `checkout.session.completed` **and**
     `checkout.session.async_payment_succeeded`
   - Copy the endpoint's signing secret (`whsec_...`).
3. **Environment variables** (Render / local .env):
   - `STRIPE_SECRET_KEY=sk_test_...`
   - `STRIPE_WEBHOOK_SECRET=whsec_...`
   - `BILLING_ENABLED=1` (already needed for accounts)
4. **Test transaction** — buy a bundle with Stripe's test card
   `4242 4242 4242 4242`, any future expiry, any CVC. Verify:
   - the pricing page shows "Buy with Stripe" (it does once the secret key is set),
   - after the redirect back, the balance increased and a `topup` ledger row appeared,
   - the webhook shows a **200** delivery in the Stripe dashboard
     (the return-page verification credits even if the webhook is delayed/broken,
     and both paths deduplicate to one credit per order).
5. **Go live** — swap in `sk_live_...` keys (same env names), flip the webhook
   toggle of your endpoint to live event types, and do one ₹99 purchase from a
   real card before announcing.

## Razorpay (primary gateway, India-native UPI/cards)

1. **Test keys** — dashboard.razorpay.com → Account & Settings → API Keys.
2. **Webhook** — Settings → Webhooks → New Webhook:
   - URL: `https://your-site/api/billing/webhook`
   - Event: `payment.captured`
   - Copy the webhook secret.
3. **Env vars:** `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`,
   `RAZORPAY_WEBHOOK_SECRET` (test keys first).
4. **Test transaction** — Razorpay's test-mode UPI/card failures/successes all
   work from the checkout modal; verify the balance and the ledger as above.
5. **Go live** — activate your account in Razorpay (KYC), switch to live keys,
   update the webhook secret if it changes.

## Taxes / compliance notes (India)

- Crypto-free transcription sales are subject to normal GST rules — confirm
  your GST registration position; Razorpay/Stripe handle settlement, not GST.
- Gateway fees (~2% for Stripe international, per Razorpay's current rates)
  come out of settlement; the credit bundles' prices were set with headroom.
- Customers' purchases appear in the `orders` + `ledger` tables for reconciliation.

## Troubleshooting quick map

| Symptom | Cause / fix |
|---|---|
| Gateway button missing on pricing page | Its `*_SECRET_KEY` env var isn't set on the running deployment |
| Payment took money, no credits | Check the webhook dashboard for failed deliveries → signature secret mismatch; else server logs for `Credited ... min`; the browser-verify path also credits, so retry the site reload |
| 503 "keys are not configured" at order creation | Keys set only on one environment (preview vs production) |
| Double credit | Cannot happen — both paths check the order row's `paid` status before crediting (tested) |
