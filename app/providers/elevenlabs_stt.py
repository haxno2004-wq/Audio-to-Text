from __future__ import annotations

import math
import os
import time

import httpx

from .base import with_retry, http_timeout
from ..schema import ProviderResult, Word
from app.config import settings

_API = "https://api.elevenlabs.io/v1/speech-to-text"


class ElevenLabs:
    """ElevenLabs Scribe v2 — currently the most accurate Tamil ASR available.

    diarize=True annotates each word with speaker_id ('speaker_0', ...); we turn
    that into turns for the consensus speaker layer (Person 1 / Person 2).
    Word confidence comes from exp(logprob). Returns seconds already; language
    code is ISO-639-3 ('tam') — normalized to 'ta' to match the other providers.
    """

    def __init__(self):
        self.name = "elevenlabs"
        self.model = settings.elevenlabs_model
        self.label = f"ElevenLabs ({self.model})"

    @classmethod
    def enabled(cls) -> bool:
        return bool(settings.elevenlabs_key or os.environ.get("ELEVENLABS_API_KEY"))

    def transcribe(self, audio_path, duration, language, progress_callback) -> ProviderResult:
        progress_callback(0.1)
        key = settings.elevenlabs_key or os.environ.get("ELEVENLABS_API_KEY")
        if not key:
            raise RuntimeError("ELEVENLABS_API_KEY is not set")

        with open(audio_path, "rb") as f:
            buf = f.read()

        data: dict[str, str] = {
            "model_id": self.model,
            "diarize": "true",
            "timestamps_granularity": "word",
            "tag_audio_events": "true",
        }
        hint = (language or "").strip().lower()
        if hint and hint not in ("auto", "detect", "multi"):
            data["language_code"] = hint
        if settings.elevenlabs_num_speakers:
            data["num_speakers"] = str(settings.elevenlabs_num_speakers)

        progress_callback(0.35)
        t0 = time.time()

        def call():
            r = httpx.post(
                _API,
                headers={"xi-api-key": key},
                data=data,
                files={"file": (str(audio_path), buf)},
                timeout=http_timeout(),
            )
            r.raise_for_status()
            return r.json()

        res = with_retry(call)
        progress_callback(0.85)

        words = []
        for w in res.get("words") or []:
            if w.get("type") == "audio_event":
                continue
            text = (w.get("text") or "").strip()
            if not text:
                continue
            lp = w.get("logprob")
            conf = max(0.3, min(0.99, math.exp(lp))) if isinstance(lp, (int, float)) else None
            words.append(Word(
                text=text,
                start=w.get("start") or 0.0,
                end=w.get("end") or 0.0,
                conf=conf,
                speaker=_spk_int(w.get("speaker_id")),
            ))

        # word speaker ids -> utterance turns for the consensus speaker layer
        lang = res.get("language_code") or hint or "auto"
        lang = {"tam": "ta", "hin": "hi", "deu": "de", "fra": "fr", "spa": "es",
                "ita": "it", "por": "pt", "nld": "nl", "rus": "ru", "tur": "tr",
                "ara": "ar", "jpn": "ja", "kor": "ko", "zho": "zh", "ben": "bn",
                "mal": "ml", "kan": "kn", "tel": "te", "mar": "mr"}.get(lang, lang)
        turns = []
        cur_speaker = None
        seg_start = None
        seg_end = None
        for w in words:
            spk = w.speaker or 0
            if spk != cur_speaker:
                if cur_speaker is not None:
                    turns.append((seg_start, seg_end, cur_speaker))
                cur_speaker, seg_start, seg_end = spk, w.start, w.end
            else:
                seg_end = max(seg_end, w.end)
        if cur_speaker is not None:
            turns.append((seg_start, seg_end, cur_speaker))

        text = res.get("text") or ""
        if not text.strip():
            raise RuntimeError("returned an empty transcript")

        progress_callback(1.0)
        return ProviderResult(
            name=self.name,
            label=self.label,
            model=self.model,
            text=text,
            words=words,
            language=lang,
            elapsed=time.time() - t0,
            turns=turns,
        )


def _spk_int(speaker_id) -> int:
    if isinstance(speaker_id, int):
        return speaker_id
    s = str(speaker_id or "")
    digits = "".join(ch for ch in s if ch.isdigit())
    return int(digits) if digits else 0


def register() -> ElevenLabs:
    return ElevenLabs()
