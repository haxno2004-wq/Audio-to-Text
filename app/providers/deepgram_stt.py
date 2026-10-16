from __future__ import annotations

import os
import time

from deepgram import DeepgramClient

from app.schema import ProviderResult, Word
from app.config import settings


class Deepgram:
    """Deepgram prerecorded Listen v1 (deepgram-sdk v7 keyword-arg client).

    - The recurring "Deepgram failed" was the BASE model ('general'/'base')
      being asked for Tamil. Base does not cover Tamil; nova-3 (default) does,
      and on nova-3 language='multi' enables code-switching.
    - Auto language: nova-3 'multi' first; if it comes back empty we re-run the
      base model with detect_language=True, then (if even that is silent) chase
      the strongest per-language alternative returned by detection.
    - Deepgram returns times in milliseconds; this provider converts to seconds.
    """

    def __init__(self):
        self.name = "deepgram"
        self.model = settings.deepgram_model
        self.label = f"Deepgram {self.model}"

    @classmethod
    def enabled(cls) -> bool:
        return bool(settings.deepgram_key or os.environ.get("DEEPGRAM_API_KEY"))

    def _request(self, client, audio_path, model, language) -> tuple[object, float]:
        with open(audio_path, "rb") as f:
            buf = f.read()
        kwargs: dict = {
            "model": model,
            "punctuate": True,
            "smart_format": True,
            "utterances": True,
            "diarize": True,
        }
        if language:
            kwargs["language"] = language
        else:
            kwargs["detect_language"] = True
        t0 = time.time()
        res = client.listen.v1.media.transcribe_file(request=buf, **kwargs)
        return res, time.time() - t0

    def _extract(self, res) -> tuple[str, str, list[Word], list[tuple[float, float, int]]]:
        meta = getattr(res, "metadata", None)
        detected = (getattr(meta, "detected_language", None) or "") if meta else ""

        results = getattr(res, "results", None)
        channels = list(getattr(results, "channels", None) or [])
        if not channels:
            raise RuntimeError("Deepgram returned no channels")
        alts = list(getattr(channels[0], "alternatives", None) or [])
        if not alts:
            raise RuntimeError("Deepgram returned no alternatives")

        best = alts[0]
        words = [
            Word(text=w.word, start=(w.start or 0.0) / 1000.0,
                 end=(w.end or 0.0) / 1000.0, conf=w.confidence,
                 speaker=getattr(w, "speaker", None))
            for w in (best.words or [])
        ]

        turns: list[tuple[float, float, int]] = []
        for u in getattr(results, "utterances", None) or []:
            spk = getattr(u, "speaker", None)
            turns.append(((u.start or 0.0) / 1000.0, (u.end or 0.0) / 1000.0, spk if spk is not None else 0))

        return best.transcript or "", detected, words, turns

    def _first_nonempty(self, *texts: str) -> str:
        for t in texts:
            if t and t.strip():
                return t
        return ""

    def transcribe(self, audio_path, duration, language, progress_callback) -> ProviderResult:
        progress_callback(0.1)
        api_key = settings.deepgram_key or os.environ.get("DEEPGRAM_API_KEY")
        if not api_key:
            raise RuntimeError("DEEPGRAM_API_KEY is not set")
        client = DeepgramClient(api_key=api_key)

        hint = (language or "").strip().lower()
        model = self.model

        if hint and hint not in ("auto", "detect", "multi"):
            progress_callback(0.3)
            res, elapsed = self._request(client, audio_path, model, hint)
            progress_callback(0.75)
            text, detected, words, turns = self._extract(res)
        elif model.startswith("nova-3"):
            # auto: nova-3 code-switching first
            progress_callback(0.3)
            res, elapsed = self._request(client, audio_path, model, settings.multi_language_token)
            progress_callback(0.65)
            text, detected, words, turns = self._extract(res)

            if not text.strip() and settings.deepgram_detect_fallback:
                progress_callback(0.8)
                res2, _ = self._request(client, audio_path, settings.deepgram_base_model, "")
                text2, detected2, words2, turns2 = self._extract(res2)
                if text2.strip():
                    text, detected, words, turns = text2, detected2, words2, turns2
        else:
            progress_callback(0.3)
            res, elapsed = self._request(client, audio_path, model, "")
            progress_callback(0.75)
            text, detected, words, turns = self._extract(res)

        if not text.strip():
            raise RuntimeError("returned an empty transcript")

        progress_callback(1.0)
        return ProviderResult(
            name=self.name,
            label=self.label,
            model=model,
            text=text,
            words=words,
            language=detected or hint or "auto",
            elapsed=elapsed,
            turns=turns,
        )


def register() -> Deepgram:
    return Deepgram()
