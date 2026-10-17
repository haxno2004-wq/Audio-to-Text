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
| `MAX_UPLOAD_MB` | upload size limit (default 500) |

Changes to `.env` apply after restarting. On Render, env changes take effect on the next deploy/restart.

### Free-tier notes (October 2026)
- **Deepgram**: new accounts get **$200 credit**, no card — the previous "Deepgram failed"
  was `language=multi` (not valid for Tamil): auto-detect now runs the base model first
  and re-runs nova-3 on the detected language.
- **Sarvam AI**: free signup credits (≈200 min). The REST endpoint takes ≤30 s per file;
  the provider chunks audio automatically.
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

## Tests
`.\.venv\Scripts\python.exe -m pip install pytest` then `.\.venv\Scripts\python.exe -m pytest tests`

## Limits
- Numbers ("5" vs "five") count as disagreements and are settled by votes.
- Thai, Lao, Khmer, Burmese are joined without spaces but vote per window, not per word.
- Your audio is sent to each cloud provider you enable. Leave a key empty to disable it.
