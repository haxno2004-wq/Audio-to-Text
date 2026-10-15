from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import httpx

from ..schema import ProviderResult, Word

RETRY_STATUS = {429, 500, 502, 503, 504}


class ProviderError(RuntimeError):
    pass


def http_timeout() -> httpx.Timeout:
    return httpx.Timeout(900.0, connect=30.0)


def with_retry(fn: Callable, attempts: int = 3):
    """Run fn(); retry transient HTTP/network failures with exponential backoff."""
    for i in range(attempts):
        last = i == attempts - 1
        try:
            return fn()
        except httpx.HTTPStatusError as e:
            if e.response.status_code not in RETRY_STATUS or last:
                raise ProviderError(f"HTTP {e.response.status_code}: {e.response.text[:200]}") from e
        except httpx.TransportError as e:
            if last:
                raise ProviderError(f"Network error: {e}") from e
        time.sleep(2 ** (i + 1))


def spread_words(text: str, start: float, end: float, conf: float | None) -> list[Word]:
    """Fallback when a provider returns a phrase without word timings."""
    parts = text.split()
    if not parts:
        return []
    step = max(end - start, 0.0) / len(parts)
    return [Word(p, start + i * step, start + (i + 1) * step, conf) for i, p in enumerate(parts)]


class Provider:
    name = ""
    label = ""

    @classmethod
    def enabled(cls) -> bool:
        raise NotImplementedError

    def transcribe(
        self,
        audio: Path,
        duration: float,
        language: str | None,
        on_progress: Callable[[float], None],
    ) -> ProviderResult:
        raise NotImplementedError
