from __future__ import annotations

import os
import time

from groq import Groq

from app.schema import ProviderResult, Word
from app.config import settings


class GroqProvider:
    """Groq cloud Whisper — the free-tier workhorse. Registered in ALL so it
    actually runs (it was written earlier but never added, so jobs only ever
    ran Deepgram + AssemblyAI)."""

    def __init__(self):
        self.name = "groq"
        self.model = settings.groq_model
        self.label = f"Groq Whisper ({self.model})"

    @classmethod
    def enabled(cls) -> bool:
        return bool(settings.groq_key or os.environ.get("GROQ_API_KEY"))

    def transcribe(self, audio_path, duration, language, progress_callback) -> ProviderResult:
        progress_callback(0.1)
        api_key = settings.groq_key or os.environ.get("GROQ_API_KEY")
        client = Groq(api_key=api_key)

        with open(audio_path, "rb") as file:
            payload = file.read()

        progress_callback(0.4)

        # language "" / None -> omit so Whisper auto-detects (incl. Tamil).
        kwargs = {
            "file": ("audio", payload),
            "model": self.model,
            "response_format": "verbose_json",
            "timestamp_granularities[]": "word",
        }
        if language and language.lower() not in ("auto", "detect", "multi"):
            kwargs["language"] = language

        t0 = time.time()
        transcript = client.audio.transcriptions.create(**kwargs)
        progress_callback(0.8)

        # Segment log-prob gives a much more honest confidence than a constant.
        seg_conf: list[float] = []
        for seg in getattr(transcript, "segments", None) or []:
            lp = getattr(seg, "avg_logprob", -1.0)
            seg_conf.append(_logprob_to_conf(float(lp)))

        words: list[Word] = []
        raw_words = getattr(transcript, "words", None) or []
        for i, w in enumerate(raw_words):
            text = _field(w, "word")
            if not text:
                continue
            conf = seg_conf[min(i, len(seg_conf) - 1)] if seg_conf else 0.9
            words.append(Word(
                text=text,
                start=float(_field(w, "start", 0.0)),
                end=float(_field(w, "end", 0.0)),
                conf=conf,
            ))

        progress_callback(1.0)
        return ProviderResult(
            name=self.name,
            label=self.label,
            model=self.model,
            text=getattr(transcript, "text", "") or "",
            words=words,
            language=getattr(transcript, "language", language) or language,
            elapsed=time.time() - t0,
        )


def _field(w, key: str, default=None):
    """Tolerate both SDK objects and dicts."""
    v = w.get(key, default) if isinstance(w, dict) else getattr(w, key, default)
    return v if v is not None else default


def _logprob_to_conf(lp: float) -> float:
    if lp >= 0:
        return 0.95
    return max(0.40, min(0.97, 1.0 + max(lp, -3.5) / 6.0))


def register() -> GroqProvider:
    return GroqProvider()
