from __future__ import annotations

import os
import time

import httpx

from ..schema import ProviderResult, Word
from ..config import settings

API_URL = "https://api.elevenlabs.io/v1/speech-to-text"


class ElevenLabs:
    """ElevenLabs Scribe v2 — top-tier accuracy, Tamil (`tam`) supported,
    per-word timestamps and speaker diarization in one call.

    Uses raw HTTP (no heavy SDK). Timestamps arrive in seconds already.
    """

    def __init__(self):
        self.name = "elevenlabs"
        self.model = settings.elevenlabs_model
        self.label = f"ElevenLabs Scribe ({self.model})"

    @classmethod
    def enabled(cls) -> bool:
        return bool(settings.elevenlabs_key or os.environ.get("ELEVENLABS_API_KEY"))

    def transcribe(self, audio_path, duration, language, progress_callback) -> ProviderResult:
        progress_callback(0.1)
        api_key = settings.elevenlabs_key or os.environ.get("ELEVENLABS_API_KEY")
        if not api_key:
            raise RuntimeError("ELEVENLABS_API_KEY is not set")

        hint = (language or "").strip().lower()
        data = {
            "model_id": self.model,
            "timestamps_granularity": "word",
            "diarize": "true",
        }
        if hint and hint not in ("auto", "detect", "multi"):
            data["language_code"] = hint

        t0 = time.time()
        with open(audio_path, "rb") as f:
            with httpx.Client(timeout=900.0) as client:
                resp = client.post(
                    API_URL,
                    headers={"xi-api-key": api_key},
                    files={"file": (audio_path.name, f, "audio/flac")},
                    data=data,
                )
                elapsed = time.time() - t0
                if resp.status_code != 200:
                    raise RuntimeError(
                        f"HTTP {resp.status_code}: {resp.text[:200]}"
                    )
                body = resp.json()
        progress_callback(0.85)

        words: list[Word] = []
        speakers: dict = {}
        turns: list[tuple[float, float, int]] = []
        for w in body.get("words") or []:
            if w.get("type") and w["type"] != "word":           # spacing/punctuation marks
                if w["type"] == "spacing":
                    continue
            spk = w.get("speaker_id")
            start, end = float(w.get("start") or 0.0), float(w.get("end") or 0.0)
            if spk is not None:
                conf = w.get("logprob")
                # Scribe gives no numeric confidence; synthesize from logprob if present
                confidence = _logprob(conf)
                words.append(Word(text=w.get("text") or "", start=start, end=end, conf=confidence,
                                  speaker=_map_speaker(spk, speakers)))
                cur = turns[-1] if turns else None
                if cur and cur[2] == speakers.get(spk, -1) and abs(cur[1] - start) < 2.0:
                    turns[-1] = (cur[0], end, cur[2])
                else:
                    sid = _map_speaker(spk, speakers)
                    turns.append((start, end, sid))

        if not words and not (body.get("text") or "").strip():
            raise RuntimeError("returned an empty transcript")

        progress_callback(1.0)
        return ProviderResult(
            name=self.name,
            label=self.label,
            model=self.model,
            text=body.get("text") or "",
            words=words,
            language=body.get("language_code") or hint or "auto",
            elapsed=elapsed,
            turns=turns,
        )


def _map_speaker(raw: str, speakers: dict) -> int:
    """Scribe speaker ids like 'speaker_A1' or 'A' -> stable small ints."""
    if raw not in speakers:
        speakers[raw] = len(speakers)
    return speakers[raw]


def _logprob(lp):
    try:
        lp = float(lp)
    except (TypeError, ValueError):
        return None
    if lp >= 0:
        return 0.95
    return max(0.40, min(0.97, 1.0 + max(lp, -3.5) / 6.0))


def register() -> ElevenLabs:
    return ElevenLabs()
