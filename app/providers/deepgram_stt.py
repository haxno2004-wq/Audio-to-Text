from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import httpx

from ..config import settings
from ..schema import ProviderResult, Word
from .base import Provider, http_timeout, with_retry

URL = "https://api.deepgram.com/v1/listen"


class Deepgram(Provider):
    name = "deepgram"
    label = f"Deepgram {settings.deepgram_model}"

    @classmethod
    def enabled(cls) -> bool:
        return bool(settings.deepgram_key)

    def transcribe(self, audio: Path, duration: float, language: str | None, on_progress: Callable[[float], None]) -> ProviderResult:
        t0 = time.time()
        lang = language or settings.deepgram_language
        params = {"model": settings.deepgram_model, "smart_format": "true", "punctuate": "true"}
        if lang in ("detect", "auto", ""):
            params["detect_language"] = "true"
        else:
            params["language"] = lang       # "multi" enables code-switching on Nova-3
        body = audio.read_bytes()

        def call():
            r = httpx.post(
                URL, params=params, content=body, timeout=http_timeout(),
                headers={"Authorization": f"Token {settings.deepgram_key}", "Content-Type": "audio/flac"},
            )
            r.raise_for_status()
            return r.json()

        data = with_retry(call)
        channel = data["results"]["channels"][0]
        alt = channel["alternatives"][0]
        words = [
            Word(w.get("punctuated_word") or w["word"], w["start"], w["end"], w.get("confidence"))
            for w in alt.get("words", [])
        ]
        detected = channel.get("detected_language") or (channel.get("languages") or [None])[0]
        return ProviderResult(
            name=self.name, label=self.label, model=settings.deepgram_model,
            text=alt.get("transcript", ""), words=words,
            language=detected or (None if lang in ("detect", "auto", "multi", "") else lang),
            elapsed=time.time() - t0,
        )
