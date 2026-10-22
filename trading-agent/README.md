# Trading agent — CoinDCX INR spot, paper-first

A small, deliberately boring trend-following agent for Indian crypto spot
markets. It was **not built to chase profit; it was built to keep a ₹500
pilot from being destroyed by fees, TDS or bad habits.**

**Honesty first:** no algorithm can be guaranteed to make money. Crypto is
highly volatile, gains are taxed at 30% (VDA rules), every sell drops 1% TDS,
and a round trip already costs ~1.35% in fees+TDS. The strategy is engineered
around that arithmetic: *rare*, *slow* trades that must clear the hurdle.
Nothing in this folder is financial advice.

## Why CoinDCX (and what about ZebPay?)

Field research ([payment check](../docs/payments-golive.md) notes in the main README):
ZebPay does offer a retail trading API now (REST at `sapi.zebpay.com`, keys with
permission scopes and IP whitelisting), and it is FIU-registered — but access is
approval-gated, its spot API docs are marked work-in-progress, its entry fee is
high (0.45%), and a public complaints board shows a backlog of unresolved
withdrawal complaints (386/464 unresolved — treat as a signal, not a verdict).
CoinDCX was chosen as the backend because its API is fully documented
(https://docs.coindcx.com), publishes machine-readable order constraints
(`min_notional`, precisions), allows algorithmic trading under its API terms,
and quotes a 2,000-orders-per-minute ceiling. If your ZebPay API application is
approved and you want to switch, the exchange is isolated in one module
(`coindcx.py`) — swap it out for a `zebpay.py`.

## Strategy (what the "agent" actually decides)

On 1-hour BTC-INR candles, on *closed* bars only:
- **Trend filter:** 12/48 EMA pair must be in a confirmed uptrend for 3 bars.
- **Entry:** price enters one ATR of a 24-bar breakout high.
- **Exit:** 2.5×ATR trailing stop that only ever ratchets upward.
- Position size is capped at ≤50% of capital (₹250 for a ₹500 pilot) and no
  more than 3 entries per day with a 4-hour cooldown; a −5% day halts trading.

Tunables are explicit env vars (`TRADE_*` in the code headers) — no magic.

## Files

| File | What it is |
|---|---|
| `coindcx.py` | REST client: public candles/tickers + HMAC-signed trading endpoints (spot only, trade-only keys) |
| `strategy.py` | Pure signal logic (EMAs, ATR, breakout) — no I/O, no state |
| `risk.py` | Guardrails: sizing, caps, cooldown, daily-loss halt, fee/TDS math |
| `ledger.py` | Paper SQLite ledger: fills with fees + TDS, trailing-stop state |
| `bot.py` | The loop: paper mode by default, LIVE_MODE=1 = real orders |
| `backtest.py` | Runs the strategy over 1,000 real fetched candles |

## Setup & run

```powershell
# from the repo root, with the app's venv
.\.venv\Scripts\python.exe trading-agent\backtest.py BTCINR 1000   # evidence
.\.venv\Scripts\python.exe trading-agent\bot.py                    # one paper cycle
.\.venv\Scripts\python.exe trading-agent\bot.py --loop             # runs every POLL_MINUTES

# scheduled forever (Task Scheduler / systemd): run --loop in a wrapper
```

Env vars for the pilot (see `.env.example`): `TRADING_CAPITAL=500`,
`TRADE_PAIR=BTCINR`, `POLL_MINUTES=15`. **Do not set `LIVE_MODE=1` without
reading the go-live section below.**

## Going from paper to live (your explicit steps, deliberately manual)

1. Run `backtest.py` — know the drawdown you tolerated.
2. Run the bot in paper mode (`--loop`) for at least 2 weeks; watch it on
   `hosts` logs; the paper ledger DB is human-readable.
3. If and only if you accept the 1.35%-per-trade hurdle and tested drawdown:
   - create a CoinDCX API key with **trade permission only, withdraw OFF**,
     IP-whitelisted to your machine,
   - set `COINDCX_API_KEY` + `COINDCX_API_SECRET` in a file the bot reads,
   - `LIVE_MODE=1 TRADING_CAPITAL=500 MAX_INR_POSITION=250` → one ₹500 pilot.
4. Weekly: reconcile the ledger against exchange fills, then reassess.
5. Kill switch: stop the process; every cap also hard-blocks worse days.

## Tests

```powershell
..\..\.venv\Scripts\python.exe -m pytest trading-agent
```
Covers: signal logic on synthetic candles (no premature buys), risk caps
and cooldown, ledger round-trip cost accounting (fees + 1% TDS on sells).
