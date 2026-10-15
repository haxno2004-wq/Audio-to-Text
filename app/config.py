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
    whisper_device: str = os.getenv("WHISPER_DEVICE", "cpu")        # cpu | cuda | auto
    whisper_compute: str = os.getenv("WHISPER_COMPUTE", "int8")
    whisper_beam: int = int(os.getenv("WHISPER_BEAM", "5"))

    # Deepgram
    deepgram_key: str = os.getenv("DEEPGRAM_API_KEY", "").strip()
    deepgram_model: str = os.getenv("DEEPGRAM_MODEL", "general")
    deepgram_language: str = os.getenv("DEEPGRAM_LANGUAGE", "ta")

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