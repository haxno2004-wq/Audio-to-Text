"""Audio helpers. Uses ffmpeg from PATH if present, otherwise the copy bundled with imageio-ffmpeg."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


class AudioError(RuntimeError):
    pass


def _ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:
        raise AudioError("ffmpeg was not found. Run start.bat again to install the bundled copy.") from e


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def normalize(src: Path, dst: Path) -> Path:
    """Any container/codec in -> 16 kHz mono FLAC out."""
    proc = _run([_ffmpeg(), "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000",
                 "-c:a", "flac", str(dst)])
    if proc.returncode != 0:
        tail = proc.stderr.strip().splitlines()[-1:] or ["unreadable file"]
        raise AudioError(f"Could not read this file as audio ({tail[0]})")
    return dst


def probe_duration(path: Path) -> float:
    try:
        import av  # installed with faster-whisper
        with av.open(str(path)) as container:
            if container.duration:
                return container.duration / av.time_base
    except Exception:
        pass
    proc = _run([_ffmpeg(), "-i", str(path)])          # prints "Duration: hh:mm:ss.xx" to stderr
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", proc.stderr)
    if not m:
        raise AudioError("Could not determine the length of this audio file")
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)
