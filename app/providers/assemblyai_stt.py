"""AssemblyAI via REST: upload -> create transcript -> poll."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import httpx

from ..config import settings
from ..schema import ProviderResult, Word
from .base import Provider, ProviderError, http_timeout, with_retry

BASE = "https://api.assemblyai.com"


class AssemblyAI(Provider):
    name = "assemblyai"
    label = "AssemblyAI Universal"

    @classmethod
    def enabled(cls) -> bool:
        return bool(settings.assemblyai_key)

    def transcribe(self, audio: Path, duration: float, language: str | None, on_progress: Callable[[float], None]) -> ProviderResult:
        t0 = time.time()
        headers = {"authorization": settings.assemblyai_key}
        body = audio.read_bytes()

        def upload():
            r = httpx.post(f"{BASE}/v2/upload", headers=headers, content=body, timeout=http_timeout())
            r.raise_for_status()
            return r.json()["upload_url"]

        audio_url = with_retry(upload)
        payload: dict = {
            "audio_url": audio_url,
            "speech_models": list(settings.assemblyai_models),  # required by the API
            "punctuate": True,
            "format_text": True,
        }
        if language:
            payload["language_code"] = language
        else:
            payload["language_detection"] = True

        def create():
            r = httpx.post(f"{BASE}/v2/transcript", headers=headers, json=payload, timeout=http_timeout())
            r.raise_for_status()
            return r.json()["id"]

        tid = with_retry(create)
        deadline = time.time() + max(900.0, duration * 3)
        while True:
            def poll():
                r = httpx.get(f"{BASE}/v2/transcript/{tid}", headers=headers, timeout=http_timeout())
                r.raise_for_status()
                return r.json()

            data = with_retry(poll)
            if data["status"] == "completed":
                break
            if data["status"] == "error":
                raise ProviderError(data.get("error", "AssemblyAI reported an error"))
            if time.time() > deadline:
                raise ProviderError("Timed out waiting for AssemblyAI")
            time.sleep(3)

        words = [Word(w["text"], w["start"] / 1000, w["end"] / 1000, w.get("confidence")) for w in data.get("words") or []]
        return ProviderResult(
            name=self.name, label=self.label, model=",".join(settings.assemblyai_models),
            text=data.get("text") or "", words=words, language=data.get("language_code"),
            elapsed=time.time() - t0,
        )
