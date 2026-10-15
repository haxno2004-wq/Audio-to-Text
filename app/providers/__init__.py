from .assemblyai_stt import AssemblyAI
from .base import Provider, ProviderError
from .deepgram_stt import Deepgram
from .whisper_local import WhisperLocal

# To add another API model: write one file with a Provider subclass and add it here.
ALL = (WhisperLocal, Deepgram, AssemblyAI)


def enabled_providers() -> list[Provider]:
    """Providers whose credentials/config are present. Missing keys simply drop that model."""
    return [cls() for cls in ALL if cls.enabled()]


def provider_status() -> list[dict]:
    return [{"name": c.name, "label": c.label, "enabled": c.enabled()} for c in ALL]
