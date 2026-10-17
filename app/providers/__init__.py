from .assemblyai_stt import AssemblyAI
from .base import Provider, ProviderError
from .deepgram_stt import Deepgram
from .elevenlabs_stt import ElevenLabs
from .groq_stt import GroqProvider
from .sarvam_stt import Sarvam
from .whisper_local import WhisperLocal

# A provider whose SDK is missing/broken on the host must not take down the whole
# service — we skip it (with a surfaced reason in /api/providers) instead.
def _import_all():
    classes = []
    problems = {}
    for mod_name, cls_name in [
        ("elevenlabs_stt", "ElevenLabs"),
        ("sarvam_stt", "Sarvam"),
        ("whisper_local", "WhisperLocal"),
        ("deepgram_stt", "Deepgram"),
        ("assemblyai_stt", "AssemblyAI"),
        ("groq_stt", "GroqProvider"),
    ]:
        try:
            m = __import__(f"app.providers.{mod_name}", fromlist=[cls_name])
            classes.append(getattr(m, cls_name))
        except Exception as e:  # ImportError, syntax, missing dep…
            problems[cls_name] = f"{type(e).__name__}: {e}"
    return classes, problems


ALL, IMPORT_ERRORS = _import_all()


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
    for cls_name, err in IMPORT_ERRORS.items():
        out.append({"name": cls_name.lower(), "label": f"{cls_name} (broken import)", "enabled": False})
    return out
