import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.consensus import build_consensus, join_tokens  # noqa: E402
from app.schema import ProviderResult, Word  # noqa: E402


def mk(name, text, conf=0.9, t0=0.0, dt=0.4, lang="en"):
    words = [Word(w, t0 + i * dt, t0 + i * dt + 0.3, conf) for i, w in enumerate(text.split())]
    return ProviderResult(name=name, label=name, model=name, text=text, words=words, language=lang)


def test_majority_wins_and_flags_disagreement():
    out = build_consensus([
        mk("a", "the quick brown fox jumps"),
        mk("b", "The quick brown fox jumps."),
        mk("c", "the quick brawn fox jumps"),
    ])
    assert out["text"].lower().replace(".", "") == "the quick brown fox jumps"
    words = {w[0].lower().strip("."): w for seg in out["segments"] for w in seg["words"]}
    assert words["brown"][1] > 0.6
    assert out["model_agreement"]["c"] < out["model_agreement"]["a"]


def test_minority_insertion_is_dropped():
    out = build_consensus([
        mk("a", "we went to the market"),
        mk("b", "we went to the market"),
        mk("c", "we went to the very big market"),
    ])
    assert out["text"] == "we went to the market"


def test_confidence_breaks_two_way_tie():
    a = mk("a", "paint it a bright color", conf=0.95)
    b = mk("b", "paint it a bright collar", conf=0.55)
    assert build_consensus([a, b])["text"].endswith("color")


def test_single_model_passthrough():
    out = build_consensus([mk("a", "hello there world")])
    assert out["text"] == "hello there world"
    assert out["agreement"] == 1.0


def test_cjk_has_no_spaces_and_votes_per_character():
    def zh(name, chars):
        words = [Word(c, i * 0.3, i * 0.3 + 0.25, 0.9) for i, c in enumerate(chars)]
        return ProviderResult(name, name, name, chars, words, "zh")
    out = build_consensus([zh("a", "今天天气很好"), zh("b", "今天天气很好"), zh("c", "今天天汽很好")])
    assert out["text"] == "今天天气很好"
    assert join_tokens(["你好，", "world", "世界"]) == "你好， world 世界"


def test_long_audio_is_windowed_and_loses_nothing():
    text = " ".join(f"w{i}" for i in range(400))      # ~160 s at 0.4 s per word
    r = [mk(n, text) for n in "abc"]
    out = build_consensus(r, window_seconds=30)
    assert len(out["segments"]) >= 4
    assert out["text"].replace("\n\n", " ").split() == text.split()


def test_timing_drift_between_systems_is_tolerated():
    base = "so today we talk about turbulence models in fluid dynamics"
    out = build_consensus([
        mk("a", base, t0=0.0), mk("b", base, t0=0.15), mk("c", base, t0=-0.1),
    ])
    assert out["text"] == base
