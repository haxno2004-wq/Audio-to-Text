#!/usr/bin/env bash
# macOS / Linux launcher (needs Python 3.10+)
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
[ -f .venv/.installed ] || { .venv/bin/pip install --upgrade pip && .venv/bin/pip install -r requirements.txt && touch .venv/.installed; }
[ -f .env ] || { cp .env.example .env; echo "Edit .env and add your API keys, then run ./start.sh again."; exit 0; }
.venv/bin/python run.py
