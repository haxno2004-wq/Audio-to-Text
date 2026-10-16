"""Configuration: values come from the .env file (or real environment variables)."""
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
                out[key.strip().lower()] = float(val)
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
    whisper_device: str = os.getenv("WHISPER_DEVICE", "cpu")        # cpu | cuda | auto
    whisper_compute: str = os.getenv("WHISPER_COMPUTE", "int8")
    whisper_beam: int = int(os.getenv("WHISPER_BEAM", "5"))

    # Groq (free tier: whisper + llama). Full large-v3 beats turbo in WER.
    groq_key: str = os.getenv("GROQ_API_KEY", "").strip()
    groq_model: str = os.getenv("GROQ_MODEL", "whisper-large-v3").strip()

    # ElevenLabs Scribe v2 (Tamil supported, word timestamps, diarization).
    # Free tier: ~4.5h of transcription per month on the API free plan.
    elevenlabs_key: str = os.getenv("ELEVENLABS_API_KEY", "").strip()
    elevenlabs_model: str = os.getenv("ELEVENLABS_MODEL", "scribe_v2").strip()

    # AI spelling polish (Groq llama). On by default; can be turned off in .env.
    polish_enabled: bool = os.getenv("POLISH_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")
    polish_model: str = os.getenv("POLISH_MODEL", "llama-3.3-70b-versatile").strip()
    polish_max_chars: int = int(os.getenv("POLISH_MAX_CHARS", "12000"))

    # Deepgram. NOTE: the base model ("general"/"base") does NOT support Tamil —
    # that mismatch was the recurring "Deepgram failed". nova-3 (default) does.
    deepgram_key: str = os.getenv("DEEPGRAM_API_KEY", "").strip()
    deepgram_model: str = os.getenv("DEEPGRAM_MODEL", "nova-3").strip()
    multi_language_token: str = os.getenv("DEEPGRAM_MULTI_LANGUAGE", "multi").strip()
    deepgram_base_model: str = os.getenv("DEEPGRAM_BASE_MODEL", "base").strip()
    deepgram_detect_fallback: bool = os.getenv("DEEPGRAM_DETECT_FALLBACK", "1").strip().lower() in ("1", "true", "yes", "on")

    # AssemblyAI: Tamil has no universal-3-5-pro entry; universal-2 covers it.
    assemblyai_key: str = os.getenv("ASSEMBLYAI_API_KEY", "").strip()
    assemblyai_models: tuple[str, ...] = _list("ASSEMBLYAI_SPEECH_MODELS", "universal-3-5-pro,universal-2")

    # Consensus
    weights: dict = field(default_factory=lambda: _weights(os.getenv(
        "MODEL_WEIGHTS", "elevenlabs=1.25,groq=1.15,whisper_local=1.1,deepgram=1.0,assemblyai=1.0")))
    window_seconds: float = float(os.getenv("CONSENSUS_WINDOW_SECONDS", "30"))

    # Speaker turns / Person 1 / Person 2
    speaker_labels_enabled: bool = os.getenv("SPEAKER_LABELS", "1").strip().lower() in ("1", "true", "yes", "on")

    # AI polish passes max ~2000 characters per chunk.
    polish_chunk_chars: int = int(os.getenv("POLISH_CHUNK_CHARS", "2000"))

    def upload_dir(self, job_id: str) -> Path:
        return self.data_dir / "uploads" / job_id

    def work_dir(self, job_id: str) -> Path:
        return self.data_dir / "work" / job_id


settings = Settings()
