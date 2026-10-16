from __future__ import annotations

import os
import time

import assemblyai as aai

from app.schema import ProviderResult, Word
from app.config import settings


class AssemblyAI:
    """AssemblyAI prerecorded.

    Tamil is not in universal-3-5-pro's supported list; universal-2 handles it,
    so both stay in speech_models (same fallback pair the docs describe) and
    the model actually used is reported back. Language flow mirrors Deepgram:
    a UI/worker hint wins; otherwise language_detection=True runs.
    """

    def __init__(self):
        self.name = "assemblyai"
        self.model = ", ".join(settings.assemblyai_models)
        self.label = "AssemblyAI (universal)"

    @classmethod
    def enabled(cls) -> bool:
        return bool(settings.assemblyai_key or os.environ.get("ASSEMBLYAI_API_KEY"))

    def transcribe(self, audio_path, duration, language, progress_callback) -> ProviderResult:
        progress_callback(0.1)
        api_key = settings.assemblyai_key or os.environ.get("ASSEMBLYAI_API_KEY")
        if not api_key:
            raise RuntimeError("ASSEMBLYAI_API_KEY is not set")

        aai.settings.api_key = api_key

        cfg_kwargs = {
            "speech_models": list(settings.assemblyai_models),
            "speaker_labels": True,
        }
        hint = (language or "").lower()
        if not hint or hint in ("auto", "detect", "multi"):
            cfg_kwargs["language_detection"] = True
        else:
            cfg_kwargs["language_code"] = hint

        config = aai.TranscriptionConfig(**cfg_kwargs)

        progress_callback(0.3)
        transcriber = aai.Transcriber()
        t0 = time.time()
        transcript = transcriber.transcribe(str(audio_path), config=config)
        progress_callback(0.8)

        if transcript.status == aai.TranscriptStatus.error:
            raise RuntimeError(f"AssemblyAI failed: {transcript.error}")

        used = getattr(transcript, "speech_model_used", "") or "?"
        display_model = used if used.startswith("universal") else self.model
        self.label = f"AssemblyAI ({display_model})"

        turns: list[tuple[float, float, int]] = []
        # speaker_labels=True gives utterances with speaker tags "A", "B", ...
        speaker_ids: dict[str, int] = {}
        for u in transcript.utterances or []:
            spk = u.speaker or "A"
            if spk not in speaker_ids:
                speaker_ids[spk] = len(speaker_ids)
            turns.append((u.start / 1000.0, u.end / 1000.0, speaker_ids[spk]))
        # also apply to words so the consensus overlay has dense coverage
        word_speaker = {spk: speaker_ids[spk] for spk in speaker_ids}

        words = []
        for w in transcript.words or []:
            spk_letter = getattr(w, "speaker", None)
            words.append(Word(
                text=w.text,
                start=w.start / 1000.0,
                end=w.end / 1000.0,
                conf=w.confidence,
                speaker=word_speaker.get(spk_letter) if spk_letter else None,
            ))

        progress_callback(1.0)
        return ProviderResult(
            name=self.name,
            label=self.label,
            model=display_model,
            text=transcript.text or "",
            words=words,
            language=getattr(transcript, "language_code", None) or hint or "auto",
            elapsed=time.time() - t0,
            turns=turns,
        )


def register() -> AssemblyAI:
    return AssemblyAI()
