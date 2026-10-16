"""AI spelling/grammar polish: Groq llama rewrites the consensus transcript lightly.

Rules of engagement (in the prompt): fix obvious mis-transcriptions of *names and
common words*, spelling and punctuation; never translate, never summarise, never
drop content; reply in the SAME language as the input.
"""
from __future__ import annotations

import logging
import re

from .config import settings

log = logging.getLogger(__name__)

_SYSTEM = (
    "You are a transcript editor. You receive a raw machine transcript. "
    "Fix only spelling mistakes, mis-spelled common words and punctuation. "
    "Never translate, never rewrite meaning, never summarise, never drop or add content. "
    "Keep proper nouns as spoken (correct obvious name spelling). "
    "Preserve the original language exactly as-is (same script), including code-switching. "
    "Reply with the corrected transcript text ONLY — no commentary, no markdown."
)

_MAX_AUDIO_CHARS = settings.polish_chunk_chars


def _chunks(text: str, size: int) -> list[str]:
    paras = text.split("\n\n")
    out, cur = [], ""
    for p in paras:
        if len(cur) + len(p) + 2 <= size or not cur:
            cur = f"{cur}\n\n{p}" if cur else p
        else:
            out.append(cur)
            cur = p
        while len(cur) > size:                      # pathological single huge paragraph
            cut = cur.rfind(" ", 0, size)
            cut = cut if cut > size // 2 else size
            out.append(cur[:cut])
            cur = cur[cut:].lstrip()
    if cur.strip():
        out.append(cur)
    return out


def polish(text: str | None, groq_key: str | None = None, model: str | None = None) -> str | None:
    """Return the polished text, or None if polishing is off/unavailable/failed."""
    if not settings.polish_enabled or not text or not text.strip():
        return None
    key = groq_key or settings.groq_key
    if not key:
        return None
    model = model or settings.polish_model
    try:
        from groq import Groq
        client = Groq(api_key=key)
    except Exception as e:                           # pragma: no cover
        log.warning("Polish skipped: %s", e)
        return None

    parts = _chunks(text, settings.polish_chunk_chars or _MAX_AUDIO_CHARS)
    out: list[str] = []
    for part in parts:
        try:
            resp = client.chat.completions.create(
                model=model,
                temperature=0.0,
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": part},
                ],
            )
            fixed = (resp.choices[0].message.content or "").strip()
            out.append(_strip_clutter(fixed) if fixed else part)
        except Exception as e:
            log.warning("Polish chunk failed, keeping raw text: %s", e)
            out.append(part)
    polished = "\n\n".join(out).strip()
    return polished or None


def _strip_clutter(s: str) -> str:
    s = re.sub(r"^```[a-zA-Z]*\n", "", s)
    s = re.sub(r"\n```$", "", s)
    return s.strip()
