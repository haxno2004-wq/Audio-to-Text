from __future__ import annotations

import logging
import os
import time

from deepgram import DeepgramClient

from app.schema import ProviderResult, Word
from app.config import settings

log = logging.getLogger(__name__)


class Deepgram:
    """Deepgram prerecorded Listen v1 (deepgram-sdk v7 keyword-arg client).

    - The recurring "Deepgram failed" had two causes: the BASE model does not
      cover Tamil, and language='multi' is only documented for nova-3's
      code-switching set (en, es, fr, de, hi, ru, pt, ja, it, nl) — NOT Tamil.
    - And the recurring "Deepgram only gives Hindi" had one cause: in auto mode
      the base model (no Tamil support) detected the language first and guessed
      Hindi (Devanagari) for Tamil audio. Fix: nova-3 now covers Tamil (added
      Jan 2026), so auto mode ALSO probes nova-3 with language='ta' whenever the
      detected transcript comes back in Devanagari, and keeps whichever run
      actually produced Tamil script. A language hint always wins directly.
    - Deepgram returns times in milliseconds; this provider converts to seconds.
    """

    # Languages documented for nova-3 code-switching ('multi') at the time of writing.
    _MULTI_SET = {"en", "es", "fr", "de", "hi", "ru", "pt", "ja", "it", "nl"}

    # Unicode blocks used to sanity-check which script a run actually produced.
    _TAMIL = (0x0B80, 0x0BFF)
    _DEVANAGARI = (0x0900, 0x097F)

    # Indic languages the base model tends to guess for Tamil audio.
    # (nova-3 supports Tamil directly — 'ta' probe converts a bad guess result
    # back into Tamil instead of leaving Hindi text in the comparison panel.)
    _PROBE_TA = {"hi", "mr", "ne", "sa"}

    def __init__(self):
        self.name = "deepgram"
        self.model = settings.deepgram_model
        self.label = f"Deepgram {self.model}"

    @classmethod
    def enabled(cls) -> bool:
        return bool(settings.deepgram_key or os.environ.get("DEEPGRAM_API_KEY"))

    def _request(self, client, audio_path, model, language) -> tuple[object, float]:
        with open(audio_path, "rb") as f:
            buf = f.read()
        kwargs: dict = {
            "model": model,
            "punctuate": True,
            "smart_format": True,
            "utterances": True,
            "diarize": True,
        }
        if language:
            kwargs["language"] = language
        else:
            kwargs["detect_language"] = True
        t0 = time.time()
        res = client.listen.v1.media.transcribe_file(request=buf, **kwargs)
        return res, time.time() - t0

    def _extract(self, res) -> tuple[str, str, list[Word], list[tuple[float, float, int]]]:
        meta = getattr(res, "metadata", None)
        detected = (getattr(meta, "detected_language", None) or "") if meta else ""

        results = getattr(res, "results", None)
        channels = list(getattr(results, "channels", None) or [])
        if not channels:
            raise RuntimeError("Deepgram returned no channels")
        alts = list(getattr(channels[0], "alternatives", None) or [])
        if not alts:
            raise RuntimeError("Deepgram returned no alternatives")

        best = alts[0]
        words = [
            Word(text=w.word, start=(w.start or 0.0) / 1000.0,
                 end=(w.end or 0.0) / 1000.0, conf=w.confidence,
                 speaker=getattr(w, "speaker", None))
            for w in (best.words or [])
        ]

        turns: list[tuple[float, float, int]] = []
        for u in getattr(results, "utterances", None) or []:
            spk = getattr(u, "speaker", None)
            turns.append(((u.start or 0.0) / 1000.0, (u.end or 0.0) / 1000.0, spk if spk is not None else 0))

        return best.transcript or "", detected, words, turns

    def _first_nonempty(self, *texts: str) -> str:
        for t in texts:
            if t and t.strip():
                return t
        return ""

    def transcribe(self, audio_path, duration, language, progress_callback) -> ProviderResult:
        progress_callback(0.1)
        api_key = settings.deepgram_key or os.environ.get("DEEPGRAM_API_KEY")
        if not api_key:
            raise RuntimeError("DEEPGRAM_API_KEY is not set")
        client = DeepgramClient(api_key=api_key)

        hint = (language or "").strip().lower()
        model = self.model

        # 'multi' is only valid for nova-3's code-switching set — never force it.
        if hint == "multi" and model.startswith("nova-3"):
            progress_callback(0.3)
            res, elapsed = self._request(client, audio_path, model, settings.multi_language_token)
            progress_callback(0.75)
            text, detected, words, turns = self._extract(res)
        elif hint and hint not in ("auto", "detect", "multi"):
            progress_callback(0.3)
            res, elapsed = self._request(client, audio_path, model, hint)
            progress_callback(0.75)
            text, detected, words, turns = self._extract(res)
        else:
            # Auto: the base model has NO Tamil, so its detection is worthless
            # for Tamil audio (it guessed Hindi in production). nova-3 covers
            # Tamil since 2026-01, so the FIRST run is nova-3 with 'ta'; the
            # detect-languages base run happens only if the probe doesn't
            # produce Tamil (i.e. the audio isn't Tamil after all).
            progress_callback(0.25)
            log.info("Deepgram auto: probing nova-3 with language=ta first")
            text, words, turns, detected, elapsed = "", [], [], "", 0.0
            base_text, base_words, base_turns, base_detected, base_elapsed = "", [], [], "", 0.0
            try:
                res_ta, t_ta = self._request(client, audio_path, model, "ta")
                text, detected, words, turns = self._extract(res_ta)
                elapsed += t_ta
            except Exception as e:
                log.warning("Deepgram nova-3 'ta' probe failed: %s", str(e)[:200])

            tamil_ok = _script_count(text, self._TAMIL) >= max(3, len(text) // 5)
            if not tamil_ok:
                log.info("Deepgram 'ta' probe produced little Tamil (chars=%d); "
                         "falling back to language detection", _script_count(text, self._TAMIL))
                progress_callback(0.45)
                res, t_b = self._request(client, audio_path, settings.deepgram_base_model, "")
                base_text, base_detected, base_words, base_turns = self._extract(res)
                base_elapsed += t_b
                elapsed += t_b
                # Re-run the better nova-3 model on the detected code when usable.
                code = _base_code(base_detected)
                if settings.deepgram_detect_fallback and code and code != "ta":
                    try:
                        progress_callback(0.6)
                        res2, _t = self._request(client, audio_path, model, code)
                        text, _d, words, turns = self._extract(res2)
                        elapsed += _t
                        detected = code
                        text = text or base_text
                    except Exception as e:
                        log.warning("Deepgram nova-3 re-run on %s failed: %s", code, str(e)[:200])
                        text, words, turns = base_text, base_words, base_turns
                        detected = base_detected
                else:
                    text, words, turns = base_text, base_words, base_turns
                    detected = base_detected
            else:
                log.info("Deepgram auto: nova-3 'ta' probe produced Tamil; keeping it")

        if not text.strip():
            raise RuntimeError("returned an empty transcript")

        progress_callback(1.0)
        return ProviderResult(
            name=self.name,
            label=self.label,
            model=model,
            text=text,
            words=words,
            language=detected or hint or "auto",
            elapsed=elapsed,
            turns=turns,
        )


def _script_count(text: str, block: tuple[int, int]) -> int:
    """How many characters of `text` fall inside a Unicode block (start, end)."""
    lo, hi = block
    return sum(1 for ch in text if lo <= ord(ch) <= hi)


def _base_code(code: str | None) -> str | None:
    """'ta' or 'en-IN' -> primary code for a nova-3 re-run; '' for 'multi'/'und'."""
    if not code:
        return None
    primary = code.split("-")[0].strip().lower()
    if primary in ("", "multi", "und", "unknown"):
        return None
    return primary


def register() -> Deepgram:
    return Deepgram()
