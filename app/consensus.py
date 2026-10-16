"""
Consensus transcript from several ASR systems (ROVER-style).

Pipeline
  1. Tokenise every system's words; normalise for comparison (case/punctuation-insensitive).
  2. Cut the timeline into ~30 s windows at silences shared by all systems, so the
     alignment DP stays small and word-boundary disagreements are rare.
  3. Per window: pick the "medoid" system as backbone, then progressively align the others
     into a confusion network (one slot per spoken word) with a DP that scores
     string similarity and time proximity.
  4. Per slot: vote.  score = ALPHA * (weighted vote share) + (1-ALPHA) * (mean confidence).
     "No word here" competes as a candidate, so insertions only survive with enough support.
  5. Emit the winning display form, plus an agreement score and the dissenting alternatives,
     so the UI can flag uncertain words.
"""
from __future__ import annotations

import bisect
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from rapidfuzz.distance import Levenshtein

from .schema import ProviderResult, Word

ALPHA = 0.7            # weight of vote share vs. confidence in the slot score
NULL_CONF = 0.5        # "confidence" of the no-word candidate
GAP_COST = 0.6         # DP cost of an insertion/deletion (substitution costs 1 - similarity)
DEFAULT_CONF = 0.75    # used when a provider gives no confidence
ALT_BELOW = 0.75       # attach alternatives to words with agreement below this
PARA_MIN_CHARS = 250
PARA_MAX_CHARS = 800
PARA_GAP = 1.0         # seconds of silence that can start a new paragraph

_CJK = "\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
_SPLIT = re.compile(f"([{_CJK}])")
# scripts written without spaces (also CJK punctuation / full-width forms)
_NOSPACE = re.compile(f"[{_CJK}\u0e00-\u0eff\u1000-\u109f\u1780-\u17ff\u3000-\u303f\uff00-\uffef]")
_SENT_END = (".", "?", "!", "\u3002", "\uff01", "\uff1f", "\u2026")


@dataclass
class Tok:
    sys: str
    text: str
    norm: str
    start: float
    end: float
    conf: float


@dataclass
class Slot:
    cands: dict[str, Tok]


def norm_token(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).casefold()
    return "".join(ch for ch in s if unicodedata.category(ch)[0] not in "PSZC")


def join_tokens(parts: list[str]) -> str:
    """Join with spaces, except between characters of scripts that don't use them."""
    out: list[str] = []
    for p in parts:
        if not p:
            continue
        if out and not (_NOSPACE.match(out[-1][-1]) and _NOSPACE.match(p[0])):
            out.append(" ")
        out.append(p)
    return "".join(out)


def _tokenize(name: str, words: list[Word]) -> list[Tok]:
    toks: list[Tok] = []
    for w in words:
        text = w.text.strip()
        if not text:
            continue
        pieces = [p for p in _SPLIT.split(text) if p]   # CJK ideographs/kana become 1 token each
        span = max(w.end - w.start, 0.0)
        for k, piece in enumerate(pieces):
            key = norm_token(piece)
            if not key:                                  # bare punctuation: glue to previous word
                if toks:
                    toks[-1].text += piece
                continue
            conf = w.conf if w.conf is not None else DEFAULT_CONF
            toks.append(Tok(name, piece, key,
                            w.start + span * k / len(pieces),
                            w.start + span * (k + 1) / len(pieces), conf))
    return toks


# --------------------------------------------------------------------------- windows

def _cut_points(systems: dict[str, list[Tok]], target: float) -> list[float]:
    spans = sorted((t.start, t.end) for toks in systems.values() for t in toks)
    if not spans:
        return []
    merged: list[list[float]] = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    gaps = [(merged[i][1], merged[i + 1][0]) for i in range(len(merged) - 1)]
    mids = [(a + b) / 2 for a, b in gaps]
    lens = [b - a for a, b in gaps]
    end, last, cuts = merged[-1][1], 0.0, []
    while end - last > 1.5 * target:
        i0 = bisect.bisect_left(mids, last + 0.5 * target)
        i1 = bisect.bisect_right(mids, last + 1.5 * target)
        cand = range(i0, i1)
        if cand and max(lens[i] for i in cand) >= 0.03:
            best = max(cand, key=lambda i: lens[i] - 0.01 * abs(mids[i] - (last + target)))
            cut = mids[best]
        else:
            cut = last + target                      # no usable silence: hard cut
        cuts.append(cut)
        last = cut
    return cuts


# --------------------------------------------------------------------------- alignment

def _sim(tok: Tok, slot: Slot) -> float:
    best = 0.0
    tc = (tok.start + tok.end) / 2
    for c in slot.cands.values():
        d = abs(tc - (c.start + c.end) / 2)
        if d > 3.0:
            continue
        s = 1.0 if tok.norm == c.norm else Levenshtein.normalized_similarity(tok.norm, c.norm)
        t = 1.0 if d <= 0.5 else max(0.0, 1.0 - (d - 0.5) / 2.0)
        best = max(best, s * (0.5 + 0.5 * t))
    return best


def _align(slots: list[Slot], toks: list[Tok]) -> list[Slot]:
    """Insert one system's tokens into the confusion network (Needleman-Wunsch)."""
    n, m = len(slots), len(toks)
    D = [[0.0] * (m + 1) for _ in range(n + 1)]
    B = [[0] * (m + 1) for _ in range(n + 1)]       # 0 = match/sub, 1 = slot skipped, 2 = token inserted
    for i in range(1, n + 1):
        D[i][0], B[i][0] = i * GAP_COST, 1
    for j in range(1, m + 1):
        D[0][j], B[0][j] = j * GAP_COST, 2
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            diag = D[i - 1][j - 1] + 1.0 - _sim(toks[j - 1], slots[i - 1])
            up = D[i - 1][j] + GAP_COST
            left = D[i][j - 1] + GAP_COST
            if diag <= up and diag <= left:
                D[i][j], B[i][j] = diag, 0
            elif up <= left:
                D[i][j], B[i][j] = up, 1
            else:
                D[i][j], B[i][j] = left, 2
    out: list[Slot] = []
    i, j = n, m
    while i > 0 or j > 0:
        move = B[i][j]
        if i > 0 and j > 0 and move == 0:
            slots[i - 1].cands[toks[j - 1].sys] = toks[j - 1]
            out.append(slots[i - 1])
            i, j = i - 1, j - 1
        elif i > 0 and move == 1:
            out.append(slots[i - 1])
            i -= 1
        else:
            out.append(Slot({toks[j - 1].sys: toks[j - 1]}))
            j -= 1
    out.reverse()
    return out


def _backbone(systems: dict[str, list[Tok]]) -> str:
    names = list(systems)
    norms = {n: [t.norm for t in systems[n]] for n in names}

    def mean_conf(n: str) -> float:
        return sum(t.conf for t in systems[n]) / len(systems[n])

    totals = {n: sum(Levenshtein.distance(norms[n], norms[m]) for m in names if m != n) for n in names}
    return min(names, key=lambda n: (totals[n], -mean_conf(n)))


# --------------------------------------------------------------------------- voting

def _decide(slot: Slot, weights: dict[str, float], total_w: float):
    groups: dict[str, list[Tok]] = {}
    for tok in slot.cands.values():
        groups.setdefault(tok.norm, []).append(tok)
    best = None
    for key, toks in groups.items():
        votes = sum(weights[t.sys] for t in toks)
        conf = sum(weights[t.sys] * t.conf for t in toks) / votes
        score = ALPHA * votes / total_w + (1 - ALPHA) * conf
        if best is None or score > best[0]:
            best = (score, votes, key, toks)
    absent = total_w - sum(weights[n] for n in slot.cands)
    null_score = ALPHA * absent / total_w + (1 - ALPHA) * NULL_CONF
    if best is None or null_score > best[0]:
        return None                                   # majority says "no word here"
    score, votes, key, toks = best
    rep = max(toks, key=lambda t: (weights[t.sys], t.conf))
    alts = []
    for k2, t2 in groups.items():
        if k2 != key:
            r2 = max(t2, key=lambda t: (weights[t.sys], t.conf))
            alts.append(f"{r2.text} ({', '.join(t.sys for t in t2)})")
    if absent > 0:
        missing = [n for n in weights if n not in slot.cands]
        alts.append(f"[nothing] ({', '.join(missing)})")
    return {"text": rep.text, "norm": key, "start": rep.start, "end": rep.end,
            "agree": votes / total_w, "alts": alts}


def _window_words(systems: dict[str, list[Tok]], weights: dict[str, float]) -> list[dict]:
    active = {n: t for n, t in systems.items() if t}
    if not active:
        return []
    base = _backbone(active)
    slots = [Slot({base: t}) for t in active[base]]
    for name in sorted(n for n in active if n != base):
        slots = _align(slots, active[name])
    total_w = sum(weights[n] for n in systems)
    decided = (_decide(s, weights, total_w) for s in slots)
    return [d for d in decided if d]


# --------------------------------------------------------------------------- public API

def _base_lang(code: str | None) -> str | None:
    return re.split(r"[-_]", code)[0].lower() if code else None


def _paragraphs(words: list[dict]) -> str:
    paras: list[list[str]] = []
    cur: list[str] = []
    size = 0
    prev_end = 0.0
    for w in words:
        gap = w["start"] - prev_end
        if cur and ((size >= PARA_MIN_CHARS and gap >= PARA_GAP) or
                    (size >= PARA_MAX_CHARS and cur[-1].endswith(_SENT_END))):
            paras.append(cur)
            cur, size = [], 0
        cur.append(w["text"])
        size += len(w["text"]) + 1
        prev_end = w["end"]
    if cur:
        paras.append(cur)
    return "\n\n".join(join_tokens(p) for p in paras)


# --------------------------------------------------------------------------- speakers

def _speaker_blocks(all_words: list[dict], results: list[ProviderResult]) -> list[dict] | None:
    """Turn mixed-provider speaker hints into Person 1 / Person 2 dialogue.

    Each consensus word takes a majority vote of the diarized turns that cover it,
    then consecutive same-speaker words are merged into blocks like
    {speaker: 1, start: .., end: .., text: "..."}. Returns None when no provider
    produced diarization, so the UI can hide the person view.
    """
    turns: list[tuple[float, float, int, float]] = []   # start, end, raw speaker id, weight
    raw_ids: set[int] = set()
    for r in results:
        for s, e, spk in r.turns or []:
            turns.append((float(s), float(e), int(spk), 1.0))
            raw_ids.add(int(spk))
    if not turns:
        return None

    def overlap(a0, a1, b0, b1):
        return max(0.0, min(a1, b1) - max(a0, b0))

    votes: list[int | None] = []
    for word in all_words:
        w0, w1 = word["start"], word["end"]
        tally: dict[int, float] = {}
        for s, e, spk, weight in turns:
            ov = overlap(w0, w1, s, e)
            if ov > 0:
                share = ov / max(w1 - w0, 1e-6)
                tally[spk] = tally.get(spk, 0.0) + weight * share
        if not tally and raw_ids:
            # fall back to nearest turn within 1.5s
            cands = [(abs(w0 - e), abs(s - w1), spk) for s, e, spk, _ in turns]
            near = min(cands, key=lambda c: c[0] + c[1])
            if near[0] < 1.5 or near[1] < 1.5:
                tally[near[2]] = 0.5
        votes.append(max(tally, key=tally.get) if tally else None)

    # Renumber raw ids in order of first appearance -> Person 1..N
    order: list[int] = []
    for v in votes:
        if v is not None and v not in order:
            order.append(v)
    person = {raw: i + 1 for i, raw in enumerate(order)}
    for word, v in zip(all_words, votes):
        word["speaker"] = person[v] if v is not None and v in person else None

    blocks: list[dict] = []
    for word in all_words:
        spk = word.get("speaker")
        if not spk:
            continue
        # attach speakerless neighbours inside a block's time range
        cur = blocks[-1] if blocks else None
        if cur and cur["speaker"] == spk and word["start"] - cur["end"] < 2.0:
            cur["text"] = join_tokens(cur["_parts"] + [word["text"]])
            cur["_parts"].append(word["text"])
            cur["end"] = word["end"]
        else:
            blocks.append({"speaker": spk, "start": word["start"], "end": word["end"],
                           "text": word["text"], "_parts": [word["text"]]})
    for b in blocks:
        b.pop("_parts", None)
        b["start"], b["end"] = round(b["start"], 2), round(b["end"], 2)
    return blocks or None


def build_consensus(results: list[ProviderResult], weights: dict[str, float] | None = None,
                    window_seconds: float = 30.0) -> dict:
    if not results:
        raise ValueError("No transcripts to merge")
    weights = {r.name: (weights or {}).get(r.name, 1.0) for r in results}
    systems = {r.name: _tokenize(r.name, r.words) for r in results}

    cuts = _cut_points(systems, window_seconds)
    windows: list[dict[str, list[Tok]]] = [{n: [] for n in systems} for _ in range(len(cuts) + 1)]
    for name, toks in systems.items():
        for t in toks:
            windows[bisect.bisect_right(cuts, (t.start + t.end) / 2)][name].append(t)

    segments: list[dict] = []
    all_words: list[dict] = []
    for win in windows:
        words = _window_words(win, weights)
        if not words:
            continue
        final_norms = [w["norm"] for w in words]
        # which system tracked the final text best in this window
        best_model = min(win, key=lambda n: (Levenshtein.distance([t.norm for t in win[n]], final_norms),
                                             -weights[n]))
        segments.append({
            "start": round(words[0]["start"], 2),
            "end": round(words[-1]["end"], 2),
            "text": join_tokens([w["text"] for w in words]),
            "agreement": round(sum(w["agree"] for w in words) / len(words), 3),
            "best_model": best_model,
            "words": [[w["text"], round(w["agree"], 2)] + ([w["alts"]] if w["alts"] and w["agree"] < ALT_BELOW else [])
                      for w in words],
        })
        all_words.extend(words)

    final_norms = [w["norm"] for w in all_words]
    denom = max(1, len(final_norms))
    model_agreement = {
        name: round(max(0.0, 1.0 - Levenshtein.distance([t.norm for t in toks], final_norms) / denom), 4)
        for name, toks in systems.items()
    }
    langs: Counter = Counter()
    for r in results:
        if _base_lang(r.language):
            langs[_base_lang(r.language)] += weights[r.name]
    return {
        "text": _paragraphs(all_words),
        "language": langs.most_common(1)[0][0] if langs else None,
        "agreement": round(sum(w["agree"] for w in all_words) / denom, 4) if all_words else 0.0,
        "segments": segments,
        "model_agreement": model_agreement,
        "speakers": _speaker_blocks(all_words, results),
    }
