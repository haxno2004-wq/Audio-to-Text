"""Configuration: values come from the .env file next to start.bat (or real environment variables)."""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")   # quiet warning on Windows


def _list(name: str, default: str) -> tuple[str, ...]:
    return tuple(x.strip() for x in os.getenv(name, default).split(",") if x.strip())


def _weights(raw: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for part in raw.split(","):
        if "=" in part:
            key, val = part.split("=", 1)
            try:
                out[key.strip()] = float(val)
            except ValueError:
                pass
    return out


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path(os.getenv("DATA_DIR", str(ROOT / "data")))
    models_dir: Path = Path(os.getenv("MODELS_DIR", str(ROOT / "models")))
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "500"))

# Local model (disabled for cloud memory safety)
    whisper_enabled: bool = os.getenv("WHISPER_ENABLED", "0") == "1"
    whisper_model: str = os.getenv("WHISPER_MODEL", "large-v3-turbo")
    whisper_device: str = os.getenv("WHISPER_DEVICE", "cpu")
    whisper_compute: str = os.getenv("WHISPER_COMPUTE", "int8")
    whisper_beam: int = int(os.getenv("WHISPER_BEAM", "5"))

### Step 3: Implement Groq Whisper Provider Make sure your providers list includes Groq instead of local Whisper. Create or update your Groq transcription provider file (e.g., inside an `app/providers/groq.py` or your provider registry):

import os
from groq import Groq
from app.schema import ProviderResult, Word

class GroqWhisperProvider:
    def __init__(self):
        self.name = "whisper"  # matches expected engine ID
        self.label = "Groq Whisper"
        self.model = "whisper-large-v3-turbo"
        self.client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

    def transcribe(self, audio_path, duration, language, progress_callback) -> ProviderResult:
        progress_callback(0.1)
        with open(audio_path, "rb") as file:
            transcript = self.client.audio.transcriptions.create(
                file=(str(audio_path), file.read()),
                model=self.model,
                response_format="verbose_json"
            )
        progress_callback(0.9)
        
        words = []
        if hasattr(transcript, "words") and transcript.words:
            for w in transcript.words:
                words.append(Word(text=w.get("word", ""), start=w.get("start", 0.0), end=w.get("end", 0.0), conf=0.95))
        
        progress_callback(1.0)
        return ProviderResult(
            name=self.name,
            label=self.label,
            model=self.model,
            text=transcript.text,
            words=words,
            language=getattr(transcript, "language", language)
        )

    # Deepgram
    deepgram_key: str = os.getenv("DEEPGRAM_API_KEY", "").strip()
    deepgram_model: str = os.getenv("DEEPGRAM_MODEL", "nova-3")
    deepgram_language: str = os.getenv("DEEPGRAM_LANGUAGE", "detect")

    # AssemblyAI
    assemblyai_key: str = os.getenv("ASSEMBLYAI_API_KEY", "").strip()
    assemblyai_models: tuple[str, ...] = _list("ASSEMBLYAI_SPEECH_MODELS", "universal-3-pro,universal-2")

    # Consensus
    weights: dict = field(default_factory=lambda: _weights(os.getenv("MODEL_WEIGHTS", "")))
    window_seconds: float = float(os.getenv("CONSENSUS_WINDOW_SECONDS", "30"))

    def upload_dir(self, job_id: str) -> Path:
        return self.data_dir / "uploads" / job_id

    def work_dir(self, job_id: str) -> Path:
        return self.data_dir / "work" / job_id


settings = Settings()
