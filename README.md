# Transcribe (no Docker)

Upload an audio file, wait, get one transcript. Local Whisper, Deepgram and AssemblyAI
transcribe it in parallel and a consensus algorithm merges the results.
One Python process runs everything (web UI, API and the background worker). No Docker, Redis or Node needed.

## Run it on Windows

1. Install Python 3.12 (once), then close and reopen PowerShell:
   `winget install -e --id Python.Python.3.12`
2. In the project folder run: `.\start.bat` (or double-click it).
3. First run only: it installs the packages (a few minutes), then opens Notepad on `.env`.
   Paste your `DEEPGRAM_API_KEY` and `ASSEMBLYAI_API_KEY`, save, close Notepad.
4. Your browser opens at http://localhost:8080. Stop with Ctrl+C or by closing the window.

Next time, just run `.\start.bat` again. macOS/Linux: `./start.sh`.

The first transcription downloads the Whisper model (about 3 GB for large-v3) into `models/`.
Uploads and job history are kept in `data/`.

### Same thing by hand
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env      # then edit .env
.\.venv\Scripts\python.exe run.py
```

## How it works

```
browser ─▶ FastAPI (:8080) ─▶ SQLite job row + in-memory queue ─▶ worker thread
                                                   │ ffmpeg → 16 kHz mono FLAC
                                                   ├─ faster-whisper (local)   ┐ parallel
                                                   ├─ Deepgram                 │ threads
                                                   └─ AssemblyAI               ┘
                                                   │ consensus.py (ROVER-style merge)
                                                   ▼
                                   final transcript + per-model outputs in SQLite
```
- Jobs run one at a time, so Whisper stays loaded between files.
- If the app is closed mid-job, unfinished jobs restart automatically next time.
- Consensus: per ~30 s window the models' words are aligned, then each word is decided by a
  weighted vote plus confidence. Words the models disagreed on are underlined in the UI.
  Details are in the docstring of `app/consensus.py`.

## Settings (`.env`)
| Setting | Meaning |
|---|---|
| `SARVAM_API_KEY` | Sarvam AI key (signup credits; great spoken Tamil) — sarvam.ai dashboard |
| `ELEVENLABS_API_KEY` | ElevenLabs Scribe v2 (top Tamil WER; free plan ≈30 min/month) |
| `DEEPGRAM_API_KEY` | Deepgram nova-3 ($200 free credit; hint path sends `ta` directly) |
| `GROQ_API_KEY` | Groq whisper-large-v3 + the AI spelling/polish pass |
| `WHISPER_ENABLED` | `1` runs faster-whisper locally (downloads the model on first job) |
| `WHISPER_MODEL` | `large-v3` (best, slow on CPU) or `small` / `base` (much faster, less accurate) |
| `MODEL_WEIGHTS` | e.g. `elevenlabs=1.25,sarvam=1.2,groq=1.15,deepgram=1` to trust a model more |
| `CONSENSUS_FOLLOW_BEST` | `1` (default): the highest-weight model's language wins and other-language runs are excluded from the vote; `0` merges everything |
| `MAX_UPLOAD_MB` | upload size limit (default 500) |

Changes to `.env` apply after restarting. On Render, env changes take effect on the next deploy/restart.

## Free hosting (Render Blueprint)

1. Push to GitHub, then on render.com choose **New + → Blueprint** and pick this repo
   (the included [render.yaml](render.yaml) defines a free web service + 1 GB disk).
2. Under **Environment**, add the API keys you have (`SARVAM_API_KEY`,
   `ELEVENLABS_API_KEY`, `DEEPGRAM_API_KEY`, `GROQ_API_KEY`, `ASSEMBLYAI_API_KEY`), then **Apply**.
3. The app binds to `0.0.0.0` automatically on Render (`run.py` reads `RENDER`),
   uploads/jobs live on the persistent disk at `/var/data`.

Free-plan notes: the service sleeps after ~15 min idle (first request wakes it),
and free instances give ~512 MB RAM — keep `WHISPER_ENABLED=0` there and let the
cloud models do the work (they run in parallel regardless).

### Free-tier notes (October 2026)
- **Sarvam AI**: free signup credits (≈200 min). The provider now uses the
  **Batch API** (`/speech-to-text/job/v1`, up to 2 h per file, with diarization)
  so the old 30-second REST cap no longer fails long recordings; it falls back
  to chunked REST only if the batch endpoints reject the account.
- **Deepgram**: new accounts get **$200 credit**, no card. nova-3 covers Tamil
  (`language=ta`); when auto-detect's base-model run comes back in Devanagari
  (the old "Deepgram only gives Hindi" bug), the provider re-probes nova-3 with
  `ta` and keeps whichever run produced Tamil script.
- **ElevenLabs Scribe**: free plan shares 10,000 credits → ≈30 min of STT per month.
- **AssemblyAI**: $50 free credit; its own rating for Tamil is only "moderate" on universal-2.

## Optional: NVIDIA GPU (not tested here)
```powershell
.\.venv\Scripts\python.exe -m pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"
```
Then set `WHISPER_DEVICE=cuda` and `WHISPER_COMPUTE=float16` in `.env`. If the GPU libraries
can't be loaded, the app falls back to CPU by itself.

## Editing the UI (optional)
The built UI is in `static/`. To change it: `cd frontend`, `npm install`, `npm run dev`
(live reload on :5173, needs the app running), then `npm run build` to update `static/`.

## Going public (paying users)

Billing is **off by default** so self-hosted/local use stays open. To sell access:

1. Set in `.env` (or Render Environment):
   - `BILLING_ENABLED=1` — turns on accounts and the pricing page
   - `FREE_MINUTES=30` — welcome grant for new signups
   - `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` — from the Razorpay dashboard (test keys first!)
   - `RAZORPAY_WEBHOOK_SECRET` — set in Razorpay → Settings → Webhooks
     (point the webhook at `https://your-site/api/billing/webhook`, subscribe to `payment.captured`)
   - `CREDIT_BUNDLES=starter|60|9900, standard|300|39900, pro|900|99900`
     (name|minutes|price in paise)
   - Optional second gateway, shown side by side on the pricing page:
     `STRIPE_SECRET_KEY` + `STRIPE_WEBHOOK_SECRET` (Stripe → Webhooks → add
     endpoint `https://your-site/api/billing/stripe/webhook`, events
     `checkout.session.completed` + `checkout.session.async_payment_succeeded`).
     Any gateway left blank simply disappears from the UI.
2. Signing up grants the free minutes; buying a bundle opens Razorpay Checkout
   (UPI/cards) or redirects to Stripe Checkout. Credits land automatically — via
   the browser-verified signature/return page or the gateway webhook,
   whichever arrives first, exactly once per order.

### Earned free minutes (rewarded ads)
Users can top up without paying: they watch a full-screen **rewarded ad**
(Google's only policy-compatible incentive format) and get `REWARD_MINUTES`
(default 1) free credits, up to `REWARD_DAILY_CAP` (default 5) per day per
account (and a looser per-IP cap so NAT/office networks don't lock people out).
Enable it by setting in `frontend/.env` before `npm run build`:
`VITE_REWARDED_NETWORK_ID=<your GAM network id>` and
`VITE_REWARDED_AD_UNIT=<rewarded unit path>` (create the rewarded ad unit in
Google Ad Manager). No ad unit configured → users claim directly, still capped.
Server-side ad-view verification is not offered by Google, so the caps + the
ledger (`kind=reward` rows) are the control loop.
3. Credits are **minutes**: successful transcriptions charge `duration + 1 s`;
   failed jobs charge nothing; hitting 0 cents (402) blocks new uploads until top-up.

### Accuracy modes
- **full** (default): every enabled model votes (maximum accuracy, ~₹60–90/hr API cost).
- **budget**: only `BUDGET_PROVIDERS` (default Sarvam + ElevenLabs Scribe) run —
  still anchored by the two strongest Tamil models, roughly half the cost.
  Offer this on cheaper tiers. Users pick per upload; `DEFAULT_MODE` sets the default.

### Ads (passive earning)

Like competitor sites (Sonix shows an ad below shared transcripts), you can earn
passively from free-tier visitors with display ads — **off by default**:

1. Apply to [Google AdSense](https://adsense.google.com). The approval content
   suite is already built in: **FAQ**, **Privacy Policy** and **Terms** pages
   (topbar links / `#faq`, `#privacy`, `#terms`) plus `frontend/public/robots.txt`.
   Before applying, replace the placeholder `CONTACT_EMAIL` in
   `frontend/src/components/Info.jsx` with your real address and rebuild
   — reviewers reject sites with fake contact info. Reviews take days to ~2 weeks.
2. Set in `.env`: `ADSENSE_CLIENT=ca-pub-XXXXXXXX`.
3. Optional: `ADS_TXT=google.com, pub-XXXXXXXX, DIRECT, f08c47fec0942fa0` (served at `/ads.txt`).
4. Create two display ad units in AdSense and put their slot ids at build time into
   `frontend/.env`: `VITE_AD_SLOT_FOOTER=1234567890` and `VITE_AD_SLOT_PRICING=9876543210`.
   Rebuild (`npm run build`).

Placements (deliberately policy-safe): below the finished transcript's model panel and
under the pricing section. Never inside transcript text or on account screens.
No ads render at all without `ADSENSE_CLIENT`, so self-hosted stays ad-free.
Reality check: small tools earn roughly $1–5 per 1,000 pageviews — worth having,
not a substitute for credit sales.

## Tests
`.\.venv\Scripts\python.exe -m pip install pytest` then `.\.venv\Scripts\python.exe -m pytest tests`

## Limits
- Numbers ("5" vs "five") count as disagreements and are settled by votes.
- Thai, Lao, Khmer, Burmese are joined without spaces but vote per window, not per word.
- Your audio is sent to each cloud provider you enable. Leave a key empty to disable it.
