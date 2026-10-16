from .assemblyai_stt import AssemblyAI
from .base import Provider, ProviderError
from .deepgram_stt import Deepgram
from .groq_stt import GroqProvider
from .whisper_local import WhisperLocal

# To add another API model: write one file with a Provider subclass and add it here.
ALL = (WhisperLocal, GroqProvider, Deepgram, AssemblyAI)


def enabled_providers() -> list[Provider]:
    """Providers whose credentials/config are present. Missing keys simply drop that model."""
    return [cls() for cls in ALL if cls.enabled()]


def provider_status() -> list[dict]:
    # Class attributes live on instances (model names in labels), so build them.
    out = []
    for cls in ALL:
        try:
            inst = cls()
            out.append({"name": inst.name, "label": inst.label, "enabled": cls.enabled()})
        except Exception:
            out.append({"name": cls.name, "label": cls.label, "enabled": cls.enabled()})
    return out
