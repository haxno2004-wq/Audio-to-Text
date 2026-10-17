from __future__ import annotations

import math
import os
import subprocess
import tempfile
import time
from pathlib import Path

import httpx

from .base import with_retry, http_timeout, spread_words
from ..schema import ProviderResult, Word
from app.config import settings

_API = "https://api.sarvam.ai/speech-to-text"

# Saaras is Sarvam's current speech model for Indian languages (Saarika v2.5
# is deprecated). Built for spoken, code-mixed Indian audio — the best free
# fit for colloquial Tamil without an international card.
_API_MODEL = settings.sarvam_model or "saaras:v4"


def _ffmpeg() -> str:
    import shutil
    found = shutil.which("ffmpeg")
    if found:
        return found
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _segments(audio_path: Path, seconds: int, out_dir: Path) -> list[Path]:
    """Cut the FLAC into <=30 s mono 16 kHz wav chunks (Sarvam REST cap: 30 s)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = out_dir / "seg%04d.wav"
    cmd = [_ffmpeg(), "-y", "-v", "error", "-i", str(audio_path),
           "-vn", "-ac", "1", "-ar", "16000",
           "-f", "segment", "-segment_time", str(seconds),
           str(pattern)]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(f"could not chunk audio for Sarvam: {proc.stderr.strip()[-200:]}")
    return sorted(out_dir.glob("seg*.wav"))


class Sarvam:
    name = "sarvam"
    label = f"Sarvam ({_API_MODEL})"

    @classmethod
    def enabled(cls) -> bool:
        return bool(settings.sarvam_key or os.environ.get("SARVAM_API_KEY"))

    def _call(self, chunk: Path, language: str) -> dict:
        data: dict[str, str] = {"model": _API_MODEL}
        if language:
            data["language_code"] = language
        r = httpx.post(
            _API,
            headers={"api-subscription-key": settings.sarvam_key or os.environ.get("SARVAM_API_KEY", "")},
            data=data,
            files={"file": (chunk.name, chunk.read_bytes())},
            timeout=http_timeout(),
        )
        r.raise_for_status()
        return r.json()

    def transcribe(self, audio_path, duration, language, progress_callback) -> ProviderResult:
        key = settings.sarvam_key or os.environ.get("SARVAM_API_KEY")
        if not key:
            raise RuntimeError("SARVAM_API_KEY is not set")

        progress_callback(0.02)
        t0 = time.time()
        chunks = _segments(Path(audio_path), 30, Path(audio_path).parent / "sarvam_chunks")
        n = max(1, len(chunks))

        words: list[Word] = []
        texts: list[str] = []
        lang = None
        offset = 0.0

        try:
            for i, chunk in enumerate(chunks):
                body = with_retry(lambda c=chunk: self._call(c, language))
                text = (body.get("transcript") or "").strip()
                texts.append(text)
                detected = body.get("language_code") or ""
                if detected and not lang:
                    lang = detected
                t0c = body.get("timestamps") or {}
                raw_words = (t0c.get("start_time_seconds"), t0c.get("end_time_seconds")) \
                    if isinstance(t0c, dict) and isinstance(t0c.get("start_time_seconds"), list) \
                    else (body.get("words") or [])
                for j, w in _iterate_words(body):
                    words.append(Word(
                        text=w["text"], start=offset + w["start"], end=offset + w["end"],
                        conf=w.get("conf"),
                    ))
                # estimate chunk length from wav size (16 kHz mono 16-bit = 32 kB/s)
                offset += chunk.stat().st_size / 32000.0
                progress_callback(0.02 + 0.94 * (i + 1) / n)
        finally:
            for c in chunks:
                try:
                    c.unlink()
                except OSError:
                    pass
            try:
                chunks[0].parent.rmdir()
            except OSError:
                pass

        text_out = " ".join(t for t in texts if t).strip()
        if not text_out:
            raise RuntimeError("returned an empty transcript")

        if not words:
            # No word timings from the API: spread text evenly across duration.
            words = spread_words(text_out, 0.0, duration or offset, None)

        progress_callback(1.0)
        return ProviderResult(
            name=self.name,
            label=self.label,
            model=_API_MODEL,
            text=text_out,
            words=words,
            language=lang or (language or None),
            elapsed=time.time() - t0,
        )


def _iterate_words(body: dict):
    """Yield {'text','start','end','conf'} from a Sarvam response, tolerating shapes.

    Forms handled:
      body['timestamps']['start_time_seconds'/'end_time_seconds'/'words'],
      body['words'] = [{'word'/'text', 'start', 'end', 'confidence'}, ...]
    """
    t0c = body.get("timestamps") or {}
    if isinstance(t0c, dict) and isinstance(t0c.get("start_time_seconds"), list):
        starts = t0c["start_time_seconds"]
        ends = t0c.get("end_time_seconds") or []
        wrds = t0c.get("words") or body.get("transcript_words") or []
        for i, wtxt in enumerate(wrds):
            if not str(wtxt).strip():
                continue
            yield {"text": str(wtxt).strip(),
                   "start": float(starts[i]) if i < len(starts) else 0.0,
                   "end": float(ends[i]) if i < len(ends) else 0.0,
                   "conf": None}
        return
    for w in body.get("words") or []:
        text = (w.get("word") or w.get("text") or "").strip()
        if not text:
            continue
        yield {"text": text, "start": float(w.get("start", 0) or 0),
               "end": float(w.get("end", 0) or 0),
               "conf": None if w.get("confidence") is None else float(w["confidence"])}


def register() -> Sarvam:
    return Sarvam()
