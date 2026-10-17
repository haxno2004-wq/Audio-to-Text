from __future__ import annotations

import os
import time

from deepgram import DeepgramClient

from app.schema import ProviderResult, Word
from app.config import settings


class Deepgram:
    """Deepgram prerecorded Listen v1 (deepgram-sdk v7 keyword-arg client).

    - The recurring "Deepgram failed" had two causes: the BASE model does not
      cover Tamil, and language='multi' is only documented for nova-3's
      code-switching set (en, es, fr, de, hi, ru, pt, ja, it, nl) — NOT Tamil.
      So: a language hint goes straight to nova-3 with that code; auto-detection
      runs base with detect_language=True first, and if the detected language is
      nova-3-capable we re-run nova-3 on it for the better transcript.
    - Deepgram returns times in milliseconds; this provider converts to seconds.
    """

    # Languages documented for nova-3 code-switching ('multi') at the time of writing.
    _MULTI_SET = {"en", "es", "fr", "de", "hi", "ru", "pt", "ja", "it", "nl"}

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

        # 'multi' is only valid for nova-3's code-switching set — never force it.
        if hint == "multi" and model.startswith("nova-3"):
            progress_callback(0.3)
            res, elapsed = self._request(client, audio_path, model, settings.multi_language_token)
            progress_callback(0.75)
            text, detected, words, turns = self._extract(res)
        elif hint and hint not in ("auto", "detect", "multi"):
            progress_callback(0.3)
            res, elapsed = self._request(client, audio_path, model, hint)
            progress_callback(0.75)
            text, detected, words, turns = self._extract(res)
        else:
            # Auto: base model detects the language (broad coverage), then the
            # better nova-3 model re-runs on the detected code when possible.
            progress_callback(0.25)
            res, elapsed = self._request(client, audio_path, settings.deepgram_base_model, "")
            base_text, detected, base_words, base_turns = self._extract(res)
            if not base_text.strip():
                raise RuntimeError("returned an empty transcript")

            if settings.deepgram_detect_fallback and detected:
                code = _base_code(detected)
                if code:
                    try:
                        progress_callback(0.6)
                        res2, _t = self._request(client, audio_path, model, code)
                        text, _d, words, turns = self._extract(res2)
                        elapsed += _t
                        detected = code
                        text = text or base_text
                    except Exception:
                        # nova-3 may reject a rare language code; base result is usable.
                        text, words, turns = base_text, base_words, base_turns
                else:
                    text, words, turns = base_text, base_words, base_turns
            else:
                text, words, turns = base_text, base_words, base_turns

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


def _base_code(code: str | None) -> str | None:
    """'ta' or 'en-IN' -> primary code for a nova-3 re-run; '' for 'multi'/'und'."""
    if not code:
        return None
    primary = code.split("-")[0].strip().lower()
    if primary in ("", "multi", "und", "unknown"):
        return None
    return primary


def register() -> Deepgram:
    return Deepgram()
