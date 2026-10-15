from __future__ import annotations

import os
from deepgram import DeepgramClient
from app.schema import ProviderResult, Word
from app.config import settings

class Deepgram:
    def __init__(self):
        self.name = "deepgram"
        self.label = f"Deepgram {settings.deepgram_model}"
        self.model = settings.deepgram_model

    @classmethod
    def enabled(cls) -> bool:
        return bool(settings.deepgram_key or os.environ.get("DEEPGRAM_API_KEY"))

    def transcribe(self, audio_path, duration, language, progress_callback) -> ProviderResult:
        progress_callback(0.1)
        api_key = settings.deepgram_key or os.environ.get("DEEPGRAM_API_KEY")
        if not api_key:
            raise RuntimeError("DEEPGRAM_API_KEY is not set")
        
        client = DeepgramClient(api_key)
        
        with open(audio_path, "rb") as file:
            buffer_data = file.read()

        payload = {"buffer": buffer_data}
        
        options = {
            "model": self.model,
            "language": "multi",  # Enables robust multi-language code-switching for Tamil-English
            "smart_format": True,
            "punctuate": True,
            "utterances": True,
        }

        progress_callback(0.4)
        response = client.listen.rest.v("1").transcribe_file(payload, options)
        progress_callback(0.8)

        res_dict = response.to_dict() if hasattr(response, "to_dict") else response
        alternatives = res_dict.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])
        alt = alternatives[0] if alternatives else {}
        
        text = alt.get("transcript", "")
        words = []
        for w in alt.get("words", []):
            words.append(Word(
                text=w.get("word", ""),
                start=w.get("start", 0.0),
                end=w.get("end", 0.0),
                conf=w.get("confidence", 0.9)
            ))

        progress_callback(1.0)
        return ProviderResult(
            name=self.name,
            label=self.label,
            model=self.model,
            text=text,
            words=words,
            language="multi"
        )

def register() -> Deepgram:
    return Deepgram()