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
| `WHISPER_MODEL` | `large-v3` (best, slow on CPU) or `turbo` / `medium` (much faster) |
| `DEEPGRAM_LANGUAGE` | `detect` (one language per file) or `multi` (switching between languages) |
| `MODEL_WEIGHTS` | e.g. `whisper=1.2,deepgram=1,assemblyai=1` to trust a model more |
| `MAX_UPLOAD_MB` | upload size limit (default 500) |

Changes to `.env` apply after restarting.

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
