"""Runs every enabled provider on the same audio, in parallel threads."""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from .providers import enabled_providers
from .schema import ProviderResult

log = logging.getLogger(__name__)


class _Progress:
    """Average of per-provider progress, throttled so we don't hammer SQLite."""

    def __init__(self, names: list[str], sink: Callable[[float], None], min_interval: float = 1.0):
        self.values = {n: 0.0 for n in names}
        self.sink, self.min_interval = sink, min_interval
        self.last = 0.0
        self.lock = threading.Lock()

    def update(self, name: str, frac: float) -> None:
        with self.lock:
            self.values[name] = max(self.values[name], min(1.0, frac))
            mean = sum(self.values.values()) / len(self.values)
            now = time.time()
            if mean >= 1.0 or now - self.last >= self.min_interval:
                self.last = now
                self.sink(mean)


def run_all(audio: Path, duration: float, language: str | None,
            sink: Callable[[float], None]) -> tuple[list[ProviderResult], list[dict]]:
    providers = enabled_providers()
    if not providers:
        raise RuntimeError("No transcription providers are enabled. Check your .env file.")
    tracker = _Progress([p.name for p in providers], sink)

    def work(p):
        try:
            res = p.transcribe(audio, duration, language, lambda f: tracker.update(p.name, f))
            if not res.words and not res.text.strip():
                raise RuntimeError("returned an empty transcript")
            tracker.update(p.name, 1.0)
            return res, None
        except Exception as e:  # one provider failing must never sink the job
            log.exception("Provider %s failed", p.name)
            tracker.update(p.name, 1.0)
            return None, {"name": p.name, "label": p.label, "error": str(e)[:300]}

    results: list[ProviderResult] = []
    errors: list[dict] = []
    with ThreadPoolExecutor(max_workers=len(providers)) as pool:
        for res, err in pool.map(work, providers):
            (results if res else errors).append(res or err)
    return results, errors
