from __future__ import annotations

import os
import assemblyai as aai
from app.schema import ProviderResult, Word
from app.config import settings

class AssemblyAI:
    def __init__(self):
        self.name = "assemblyai"
        self.label = "AssemblyAI"
        self.model = "universal"

    def transcribe(self, audio_path, duration, language, progress_callback) -> ProviderResult:
        progress_callback(0.1)
        api_key = settings.assemblyai_key or os.environ.get("ASSEMBLYAI_API_KEY")
        if not api_key:
            raise RuntimeError("ASSEMBLYAI_API_KEY is not set")
        
        aai.settings.api_key = api_key
        
        # Configure transcription with language support for Tamil/English mix
        config = aai.TranscriptionConfig(
            language_code="ta",
            speech_model=aai.SpeechModel.universal
        )

        progress_callback(0.3)
        transcriber = aai.Transcriber()
        transcript = transcriber.transcribe(str(audio_path), config=config)
        
        if transcript.status == aai.TranscriptStatus.error:
            raise RuntimeError(f"AssemblyAI failed: {transcript.error}")

        progress_callback(0.8)

        words = []
        if transcript.words:
            for w in transcript.words:
                words.append(Word(
                    text=w.text,
                    start=w.start / 1000.0,
                    end=w.end / 1000.0,
                    conf=w.confidence
                ))

        progress_callback(1.0)
        return ProviderResult(
            name=self.name,
            label=self.label,
            model=self.model,
            text=transcript.text or "",
            words=words,
            language="ta"
        )

def register() -> AssemblyAI:
    return AssemblyAI()