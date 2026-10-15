from __future__ import annotations

import os
from deepgram import DeepgramClient
from app.schema import ProviderResult, Word
from app.config import settings

class Deepgram:
    def __init__(self):
        self.name = "deepgram"
        self.label = "Deepgram General (Tamil)"
        # Use the "general" model which fully supports Tamil language transcription
        self.model = "general"

    @classmethod
    def enabled(cls) -> bool:
        return bool(settings.deepgram_key or os.environ.get("DEEPGRAM_API_KEY"))

    def transcribe(self, audio_path, duration, language, progress_callback) -> ProviderResult:
        progress_callback(0.1)
        api_key = settings.deepgram_key or os.environ.get("DEEPGRAM_API_KEY")
        if not api_key:
            raise RuntimeError("DEEPGRAM_API_KEY is not set")
        
        client = DeepgramClient(api_key=api_key)
        
        with open(audio_path, "rb") as file:
            audio_bytes = file.read()

        # Configured with model="general" and language="ta" as required by Deepgram's routing
        options = {
            "model": self.model,
            "language": "ta",
            "smart_format": True,
            "punctuate": True,
            "utterances": True,
        }

        progress_callback(0.4)
        response = client.listen.v1.media.transcribe_file(request=audio_bytes, **options)
        progress_callback(0.8)

        text = ""
        words = []
        try:
            channels = response.results.channels
            if channels and len(channels) > 0:
                alternatives = channels[0].alternatives
                if alternatives and len(alternatives) > 0:
                    alt = alternatives[0]
                    text = getattr(alt, "transcript", "")
                    raw_words = getattr(alt, "words", [])
                    if raw_words:
                        for w in raw_words:
                            words.append(Word(
                                text=getattr(w, "word", ""),
                                start=getattr(w, "start", 0.0),
                                end=getattr(w, "end", 0.0),
                                conf=getattr(w, "confidence", 0.9)
                            ))
        except (AttributeError, IndexError):
            pass

        if not text.strip():
            raise RuntimeError("returned an empty transcript")

        progress_callback(1.0)
        return ProviderResult(
            name=self.name,
            label=self.label,
            model=self.model,
            text=text,
            words=words,
            language="ta"
        )

def register() -> Deepgram:
    return Deepgram()