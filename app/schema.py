"""Plain data containers shared by providers and the consensus module."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Word:
    text: str
    start: float          # seconds
    end: float            # seconds
    conf: float | None = None
    speaker: int | None = None   # diarized speaker id, when the provider knows


@dataclass
class ProviderResult:
    name: str             # short id: whisper | groq | deepgram | assemblyai
    label: str            # human label for the UI
    model: str
    text: str
    words: list[Word]
    language: str | None
    elapsed: float = 0.0
    # [(start, end, speaker_id)] utterance turns from diarization, if any
    turns: list[tuple[float, float, int]] = field(default_factory=list)
