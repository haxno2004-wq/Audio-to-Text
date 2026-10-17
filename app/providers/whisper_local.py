"""Local model: faster-whisper. Loaded once and kept in memory between jobs."""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable

from ..config import settings
from ..schema import ProviderResult, Word
from .base import Provider

log = logging.getLogger(__name__)
_model = None
_force_cpu = False
_lock = threading.Lock()


def _add_nvidia_dll_dirs() -> None:
    """Windows: make pip-installed CUDA libraries (nvidia-cublas-cu12, nvidia-cudnn-cu12) findable."""
    if os.name != "nt":
        return
    import importlib.util
    for pkg in ("nvidia.cublas", "nvidia.cudnn"):
        try:
            spec = importlib.util.find_spec(pkg)
        except Exception:
            continue
        for base in (spec.submodule_search_locations or []) if spec else []:
            bin_dir = os.path.join(base, "bin")
            if os.path.isdir(bin_dir):
                os.add_dll_directory(bin_dir)
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")


def _get_model():
    global _model
    with _lock:
        if _model is None:
            from faster_whisper import WhisperModel

            device = "cpu" if _force_cpu else settings.whisper_device
            compute = "int8" if _force_cpu else settings.whisper_compute
            if device != "cpu":
                _add_nvidia_dll_dirs()
            settings.models_dir.mkdir(parents=True, exist_ok=True)
            _model = WhisperModel(settings.whisper_model, device=device, compute_type=compute,
                                  download_root=str(settings.models_dir))
        return _model


def _to_array(audio: Path):
    """Decode to 16 kHz mono float32 via ffmpeg.

    Hand faster-whisper a numpy array: its decode_audio() path uses PyAV kwargs
    that newer av builds (Python 3.14 wheels ship av 19) have removed.
    """
    import numpy as np
    import subprocess
    import shutil

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        try:
            import imageio_ffmpeg
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception as e:
            raise RuntimeError(f"ffmpeg required for local Whisper: {e}") from e
    proc = subprocess.run(
        [ffmpeg, "-v", "error", "-i", str(audio), "-vn", "-ac", "1", "-ar", "16000",
         "-f", "s16le", "pipe:1"],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout:
        raise RuntimeError(f"could not decode audio for local Whisper: {proc.stderr[-120:]!r}")
    return np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0


class WhisperLocal(Provider):
    name = "whisper"
    label = f"Whisper {settings.whisper_model} (local)"

    @classmethod
    def enabled(cls) -> bool:
        return settings.whisper_enabled

    def _decode(self, audio: Path, duration: float, language: str | None, on_progress):
        model = _get_model()
        segments, info = model.transcribe(
            _to_array(audio),
            beam_size=settings.whisper_beam,
            word_timestamps=True,
            vad_filter=True,
            language=language,
            multilingual=language is None,
            condition_on_previous_text=False,
        )
        words: list[Word] = []
        pieces: list[str] = []
        for seg in segments:  # lazy generator: decoding happens while iterating
            pieces.append(seg.text.strip())
            for w in seg.words or []:
                words.append(Word(w.word.strip(), w.start, w.end, w.probability))
            if duration > 0:
                on_progress(min(0.99, seg.end / duration))
        return words, pieces, info.language

    def transcribe(self, audio: Path, duration: float, language: str | None,
                   on_progress: Callable[[float], None]) -> ProviderResult:
        global _model, _force_cpu
        t0 = time.time()
        try:
            words, pieces, lang = self._decode(audio, duration, language, on_progress)
        except RuntimeError as e:
            gpu_problem = any(k in str(e).lower() for k in ("cublas", "cudnn", "cuda"))
            if _force_cpu or settings.whisper_device == "cpu" or not gpu_problem:
                raise
            log.warning("GPU libraries unavailable (%s). Falling back to CPU.", e)
            with _lock:
                _model, _force_cpu = None, True
            words, pieces, lang = self._decode(audio, duration, language, on_progress)
        return ProviderResult(
            name=self.name, label=self.label, model=settings.whisper_model,
            text=" ".join(p for p in pieces if p), words=words, language=lang,
            elapsed=time.time() - t0,
        )
