"""Plain data containers shared by providers and the consensus module."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Word:
    text: str
    start: float          # seconds
    end: float            # seconds
    conf: float | None = None


@dataclass
class ProviderResult:
    name: str             # short id: whisper | deepgram | assemblyai
    label: str            # human label for the UI
    model: str
    text: str
    words: list[Word]
    language: str | None
    elapsed: float = 0.0
