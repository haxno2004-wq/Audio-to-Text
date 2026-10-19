"""Sarvam AI speech-to-text via their BATCH API (speech-to-text/job/v1).

Why the rewrite: the plain REST endpoint caps uploads at 30 s of audio, which
was the recurring "audio duration exceeds the maximum limit of 30 seconds"
error on the last job. The batch flow accepts up to 2 h per file and supports
speaker diarization, so the whole file goes up in one job.

Documented flow (Sarvam Batch API guide, docs.sarvam.ai):
  1. POST /speech-to-text/job/v1                        -> create job (job_id)
  2. POST /speech-to-text/job/v1/{id}/data-upload       -> upload the audio (multipart)
  3. POST /speech-to-text/job/v1/{id}/start
  4. GET  /speech-to-text/job/v1/{id}/status            -> poll every few seconds
  5. POST /speech-to-text/job/v1/{id}/get-transcript    -> transcribed output
If the batch flow is unavailable on the account/tier (or an endpoint 404s due
to an API revision), the provider falls back to chunked 28 s REST mode.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from pathlib import Path

import httpx

from .base import with_retry, http_timeout, spread_words
from ..schema import ProviderResult, Word
from app.config import settings

log = logging.getLogger(__name__)

_API = "https://api.sarvam.ai"

# Saaras is Sarvam's current speech model for Indian languages. Built for
# spoken, code-mixed Indian audio — the best free fit for colloquial Tamil.
_API_MODEL = settings.sarvam_model or "saaras:v4"

_POLL_INTERVAL = 5.0
_POLL_MAX = 15 * 60          # cap the batch wait; long files can take a while


def _ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _segments(audio_path: Path, seconds: int, out_dir: Path) -> list[Path]:
    """Cut the FLAC into <=seconds-long mono 16 kHz wav chunks (chunked REST fallback)."""
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


def _auth_headers() -> dict:
    key = settings.sarvam_key or os.environ.get("SARVAM_API_KEY", "")
    return {"api-subscription-key": key}


def _spk_int(spk) -> int:
    if isinstance(spk, int):
        return spk
    s = str(spk or "")
    digits = "".join(ch for ch in s if ch.isdigit())
    return int(digits) if digits else 0


def _clean_lang(code) -> str | None:
    """Sarvam returns BCP-47 like 'ta-IN'; normalize to 'ta' like the other providers."""
    if not code:
        return None
    return str(code).split("-")[0].split("_")[0].lower() or None


def _sarvam_lang(hint: str | None) -> str | None:
    """'ta' -> 'ta-IN' (Sarvam's BCP-47 style); pass anything else through."""
    base = _clean_lang(hint)
    if not base or base in ("auto", "unknown"):
        return "unknown" if hint else None
    return f"{base}-IN" if base in ("ta", "te", "kn", "ml", "hi", "bn", "mr", "gu", "pa", "or") else base


class Sarvam:
    name = "sarvam"
    label = f"Sarvam ({_API_MODEL}, batch)"

    @classmethod
    def enabled(cls) -> bool:
        return bool(settings.sarvam_key or os.environ.get("SARVAM_API_KEY"))

    # ------------------------------------------------------------------ batch flow

    def _job_create(self, language: str | None) -> dict:
        """Create a batch job. Retries once without/with 'unknown' language on a 400."""
        params: dict = {"model": _API_MODEL, "mode": "transcribe",
                        "with_timestamps": True, "with_diarization": True}
        code = _sarvam_lang(language)
        if code:
            params["language_code"] = code
        r = httpx.post(f"{_API}/speech-to-text/job/v1",
                       headers=_auth_headers(), json={"job_parameters": params},
                       timeout=http_timeout())
        if r.status_code == 400 and "language_code" in params:
            # The locale variant may be rejected on some plans; retry with auto-detect.
            params["language_code"] = "unknown"
            r = httpx.post(f"{_API}/speech-to-text/job/v1",
                           headers=_auth_headers(), json={"job_parameters": params},
                           timeout=http_timeout())
        r.raise_for_status()
        body = r.json()
        job_id = body.get("job_id") or body.get("jobId") or (body.get("job") or {}).get("id")
        if not job_id:
            raise RuntimeError(f"batch job init returned no job id: {str(body)[:200]}")
        return job_id

    def _job_upload(self, job_id: str, path: Path) -> None:
        buf = path.read_bytes()
        r = httpx.post(
            f"{_API}/speech-to-text/job/v1/{job_id}/data-upload",
            headers=_auth_headers(),
            files={"file": (path.name, buf, "audio/x-flac")},
            timeout=http_timeout(),
        )
        if r.status_code == 404:        # some API revisions renamed the upload route
            r = httpx.post(
                f"{_API}/speech-to-text/job/v1/{job_id}/upload",
                headers=_auth_headers(),
                files={"file": (path.name, buf, "audio/x-flac")},
                timeout=http_timeout(),
            )
        r.raise_for_status()

    def _job_start(self, job_id: str) -> None:
        r = httpx.post(f"{_API}/speech-to-text/job/v1/{job_id}/start",
                       headers=_auth_headers(), timeout=http_timeout())
        r.raise_for_status()

    def _job_status(self, job_id: str) -> tuple[str, dict]:
        r = httpx.get(f"{_API}/speech-to-text/job/v1/{job_id}/status",
                      headers=_auth_headers(), timeout=http_timeout())
        r.raise_for_status()
        body = r.json()
        details = body.get("job_details") or (body.get("job") or {})
        state = (body.get("status") or details.get("status") or "").lower()
        return state, body

    def _job_fetch_transcript(self, job_id: str) -> tuple[str, list[Word], list[tuple[float, float, int]]]:
        """Fetch the finished batch job's transcript + words + speaker turns."""
        r = httpx.post(f"{_API}/speech-to-text/job/v1/{job_id}/get-transcript",
                       headers=_auth_headers(), timeout=http_timeout())
        if r.status_code == 404:        # older deployments only expose download-files
            r = httpx.post(f"{_API}/speech-to-text/job/v1/download-files",
                           headers=_auth_headers(), json={"job_id": job_id},
                           timeout=http_timeout())
        r.raise_for_status()
        return _parse_batch(r.json())

    # ------------------------------------------------------------- REST chunk mode

    def _call(self, chunk: Path, language: str) -> dict:
        data: dict[str, str] = {"model": _API_MODEL, "with_timestamps": "true"}
        if language:
            data["language_code"] = language
        r = httpx.post(
            f"{_API}/speech-to-text",
            headers=_auth_headers(),
            data=data,
            files={"file": (chunk.name, chunk.read_bytes())},
            timeout=http_timeout(),
        )
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------------ entry point

    def transcribe(self, audio_path, duration, language, progress_callback) -> ProviderResult:
        key = settings.sarvam_key or os.environ.get("SARVAM_API_KEY")
        if not key:
            raise RuntimeError("SARVAM_API_KEY is not set")

        progress_callback(0.02)
        t0 = time.time()
        path = Path(audio_path)

        # ------- batch path (no 30 s limit) — primary ------- #
        try:
            return self._transcribe_batch(path, language, progress_callback, t0)
        except (httpx.HTTPStatusError, httpx.TransportError, RuntimeError) as e:
            # The batch flow is primary; on unavailable endpoints/tier/revisions,
            # fall back to 28 s chunked REST so the model still contributes.
            log.warning("Sarvam batch flow unavailable (%s); falling back to chunked REST", str(e)[:200])

        # ------- chunked REST fallback ------- #
        chunks = _segments(path, 28, path.parent / "sarvam_chunks")
        n = max(1, len(chunks))
        words: list[Word] = []
        texts: list[str] = []
        lang = None
        offset = 0.0
        try:
            for i, chunk in enumerate(chunks):
                body = with_retry(lambda c=chunk: self._call(c, _sarvam_lang(language) or ""))
                text = (body.get("transcript") or "").strip()
                texts.append(text)
                detected = _clean_lang(body.get("language_code"))
                if detected and not lang:
                    lang = detected
                for w in _iterate_words(body):
                    words.append(Word(text=w["text"], start=offset + w["start"],
                                      end=offset + w["end"], conf=w.get("conf")))
                offset += chunk.stat().st_size / 32000.0     # 16 kHz mono 16-bit ≈ 32 kB/s
                progress_callback(0.02 + 0.94 * (i + 1) / n)
        finally:
            shutil.rmtree(chunks[0].parent, ignore_errors=True)

        text_out = " ".join(t for t in texts if t).strip()
        if not text_out:
            raise RuntimeError("returned an empty transcript")
        if not words:
            words = spread_words(text_out, 0.0, duration or offset, None)
        progress_callback(1.0)
        return ProviderResult(
            name=self.name, label=self.label, model=_API_MODEL,
            text=text_out, words=words,
            language=lang or _sarvam_lang(language),
            elapsed=time.time() - t0,
        )

    def _transcribe_batch(self, path: Path, language, progress_callback, t0: float) -> ProviderResult:
        job_id = self._job_create(language)
        progress_callback(0.08)
        self._job_upload(job_id, path)
        progress_callback(0.3)
        self._job_start(job_id)
        progress_callback(0.35)

        deadline = time.time() + _POLL_MAX
        state, body = "", {}
        while time.time() < deadline:
            time.sleep(_POLL_INTERVAL)
            state, body = self._job_status(job_id)
            if state in ("success", "completed", "finished", "done", "succeeded"):
                break
            if state in ("failed", "failure", "error", "cancelled", "canceled"):
                msg = ""
                jd = body.get("job_details") or body.get("job") or {}
                for o in jd.get("outputs") or []:
                    msg = o.get("error_message") or msg
                    if msg:
                        break
                raise RuntimeError(f"batch job failed: {msg or state}")
        else:
            raise RuntimeError(f"batch job timed out after {_POLL_MAX:.0f}s (state={state!r})")
        progress_callback(0.9)

        text, words, turns = self._job_fetch_transcript(job_id)
        if not text.strip():
            raise RuntimeError("batch job returned an empty transcript")
        progress_callback(1.0)
        return ProviderResult(
            name=self.name, label=self.label, model=_API_MODEL,
            text=text, words=words, language=_sarvam_lang(language) or "auto",
            elapsed=time.time() - t0, turns=turns,
        )


def _parse_batch(body: dict):
    """Extract transcript + Word tokens (+ speaker turns) from batch output JSON.

    Shapes handled:
      - {"transcript": "...", "timestamps": {"chunks"/"words", start_time_seconds, end_time_seconds}}
      - {"transcripts": [{"transcript": ..., "timestamps": {...}, "diarized_transcript": {...}}]}
      - diarized_transcript: {"chunks"/"segments": [{"text", start/end_time_seconds, "speaker"}]}
    """
    main = body
    if isinstance(body.get("transcripts"), list) and body["transcripts"]:
        main = body["transcripts"][0]
    text = (main.get("transcript") or main.get("text") or "").strip()
    if not text:
        raise RuntimeError(f"batch output had no transcript: {str(body)[:200]}")

    words: list[Word] = []
    turns: list[tuple[float, float, int]] = []
    ts = main.get("timestamps") or {}
    chunks_txt = ts.get("chunks") or ts.get("words") or []
    starts = ts.get("start_time_seconds") or []
    ends = ts.get("end_time_seconds") or []
    for i, txt in enumerate(chunks_txt):
        s = float(starts[i]) if i < len(starts) else 0.0
        e = float(ends[i]) if i < len(ends) else s + 2.0
        words.extend(spread_words(str(txt), s, e, None))

    dia = main.get("diarized_transcript") or {}
    segs = dia.get("chunks") or dia.get("segments") or []
    for seg in segs:
        s = float(seg.get("start_time_seconds", 0) or 0)
        e = float(seg.get("end_time_seconds", 0) or 0)
        spk = _spk_int(seg.get("speaker") or seg.get("speaker_id") or 0)
        if e > s:
            turns.append((s, e, spk))
    if not turns and isinstance(ts.get("speakers"), list):
        spks = ts["speakers"]
        for i, txt in enumerate(chunks_txt):
            s = float(starts[i]) if i < len(starts) else 0.0
            e = float(ends[i]) if i < len(ends) else s + 2.0
            turns.append((s, e, _spk_int(spks[i]) if i < len(spks) else 0))

    return text, words, turns


def _iterate_words(body: dict):
    """Legacy REST response: yield {'text','start','end','conf'} tolerating shapes."""
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
