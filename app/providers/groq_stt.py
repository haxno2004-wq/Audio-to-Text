from __future__ import annotations

import os
from groq import Groq
from app.schema import ProviderResult, Word
from app.config import settings

class GroqWhisperProvider:
    def __init__(self):
        self.name = "whisper"
        self.label = "Groq Whisper"
        self.model = "whisper-large-v3-turbo"
        self.client = Groq(api_key=os.environ.get("GROQ_API_KEY", settings.deepgram_key))

    def transcribe(self, audio_path, duration, language, progress_callback) -> ProviderResult:
        progress_callback(0.1)
        
        with open(audio_path, "rb") as file:
            # We explicitly pass language="ta" to handle Tamil and English mixed code-switching accurately
            transcript = self.client.audio.transcriptions.create(
                file=(str(audio_path), file.read()),
                model=self.model,
                language="ta",  
                response_format="verbose_json"
            )
            
        progress_callback(0.8)
        
        words = []
        raw_words = getattr(transcript, "words", None)
        if raw_words:
            for w in raw_words:
                # Handle both object attributes and dictionary keys safely
                w_text = w.get("word") if isinstance(w, dict) else getattr(w, "word", "")
                w_start = w.get("start") if isinstance(w, dict) else getattr(w, "start", 0.0)
                w_end = w.get("end") if isinstance(w, dict) else getattr(w, "end", 0.0)
                words.append(Word(text=w_text, start=w_start, end=w_end, conf=0.95))
        
        progress_callback(1.0)
        
        return ProviderResult(
            name=self.name,
            label=self.label,
            model=self.model,
            text=getattr(transcript, "text", ""),
            words=words,
            language=getattr(transcript, "language", "ta")
        )

def register() -> GroqWhisperProvider:
    return GroqWhisperProvider()