import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import speech_cuts as sc  # noqa: E402

SR = sc.SR


def _audio(pattern):
    """pattern = [(seconds, loud?)] -> 16 kHz samples: 220 Hz tone for speech, faint noise for room tone."""
    rng = np.random.default_rng(0)
    parts = []
    for secs, loud in pattern:
        n = int(secs * SR)
        t = np.arange(n) / SR
        parts.append(0.3 * np.sin(2 * np.pi * 220 * t) if loud else 0.0005 * rng.standard_normal(n))
    return np.concatenate(parts).astype(np.float32)


def _words(spec):
    return [{"word": w, "start": s, "end": e} for w, s, e in spec]


def test_silent_runs_and_threshold():
    db = sc.rms_db(_audio([(1, True), (1, False), (1, True)]))
    runs = sc.silent_runs(db, sc.silence_threshold(db), 0.5)
    assert len(runs) == 1
    assert runs[0][0] == pytest.approx(1.0, abs=0.02) and runs[0][1] == pytest.approx(2.0, abs=0.02)


def test_silence_cuts_keep_a_breath_and_trim_head_tail():
    samples = _audio([(0.8, False), (1, True), (1.0, False), (1, True), (0.3, False), (1, True), (1.2, False)])
    words = _words([("Hello.", 0.8, 1.8), ("again", 2.8, 3.8), ("now", 4.1, 5.1)])
    db = sc.rms_db(samples)
    cuts = sc.silence_cuts(words, db, len(samples) / SR)
    kinds = [c["type"] for c in cuts]
    assert kinds == ["head", "pause", "tail"]  # the 0.3s pause is natural rhythm, left alone
    head, pause, tail = (c["cut"] for c in cuts)
    assert head == pytest.approx([0.0, 0.8 - 0.22], abs=0.02)
    assert pause[1] - pause[0] == pytest.approx(1.0 - 0.20, abs=0.02)  # sentence end keeps 0.20s
    assert tail[0] == pytest.approx(5.1 + 0.34, abs=0.02)


def test_breath_override():
    samples = _audio([(1, True), (1.0, False), (1, True)])
    cuts = sc.silence_cuts(_words([("a", 0, 1), ("b", 2, 3)]), sc.rms_db(samples), 3.0, breath=0.15)
    assert cuts[0]["cut"][1] - cuts[0]["cut"][0] == pytest.approx(0.85, abs=0.02)


def test_stutter_and_emphasis_both_flagged_for_review():
    words = _words([("the", 0.0, 0.2), ("the", 0.3, 0.5), ("cream", 0.6, 1.0)])
    c = sc.mistake_cuts(words)
    assert len(c) == 1 and c[0]["type"] == "stutter" and c[0]["cut"] == [0.0, 0.3]


def test_retake_keeps_the_later_take():
    take = "this collagen powder finally fixed my heel pain every single morning".split()
    words, t = [], 0.0
    for w in take[:6]:  # botched first take
        words.append({"word": w, "start": t, "end": t + 0.3}); t += 0.35
    t += 1.5
    second = t
    for w in take:
        words.append({"word": w, "start": t, "end": t + 0.3}); t += 0.35
    c = [x for x in sc.mistake_cuts(words) if x["type"] in ("retake", "false_start")]
    assert c and c[0]["cut"] == [0.0, second] and c[0]["type"] == "false_start"


def test_snap_edge_moves_into_quiet():
    db = sc.rms_db(_audio([(1, True), (0.2, False), (1, True)]))
    assert sc.snap_edge(db, 1.05, window=0.15) == pytest.approx(1.1, abs=0.1)
    assert 1.0 <= sc.snap_edge(db, 0.95, window=0.15) <= 1.2


def test_keep_segments_are_frame_exact_and_contiguous():
    segs = sc.keep_segments(10.0, [[1.0, 2.013], [5.5, 6.0], [9.99, 10.0]])
    assert [s["from_frame"] for s in segs][0] == 0
    for a, b in zip(segs, segs[1:]):
        assert a["to_frame"] == b["from_frame"]  # back to back, no gaps
        assert b["at"] == pytest.approx(b["from_frame"] / 30)
    for s in segs:
        assert round((s["src_out"] - s["src_in"]) * 30, 6) == s["to_frame"] - s["from_frame"]
    assert len(segs) == 3  # the 0.01s tail sliver is dropped


def test_apply_respects_review_and_reject_and_retimes_words():
    data = {"media": "x.mp4", "duration": 6.0,
            "words": _words([("one", 0.5, 0.9), ("two", 2.5, 2.9), ("three", 4.5, 4.9)]),
            "candidates": [
                {"id": "c001", "type": "pause", "cut": [1.0, 2.0], "recommend": "cut"},
                {"id": "c002", "type": "retake", "cut": [2.4, 3.0], "recommend": "review"},
                {"id": "c003", "type": "stutter", "cut": [4.0, 4.4], "recommend": "cut"}]}
    res = sc.apply(data, approve=set(), reject={"c003"})
    assert res["applied"] == ["c001"]
    assert res["removed"] == pytest.approx(1.0, abs=0.04)
    assert [w["word"] for w in res["words"]] == ["one", "two", "three"]
    assert res["words"][1]["start"] == pytest.approx(1.5, abs=0.04)
    res2 = sc.apply(data, approve={"c002"}, reject=set())
    assert "two" not in [w["word"] for w in res2["words"]]


def test_propose_end_to_end_on_synthetic_audio():
    samples = _audio([(1, False), (1, True), (1.5, False), (1, True), (1, False)])
    words = _words([("Hi.", 1.0, 2.0), ("there", 3.5, 4.5)])
    data = sc.propose(Path("x.wav"), words, samples)
    assert [c["id"] for c in data["candidates"]] == ["c001", "c002", "c003"]
    res = sc.apply(data, set(), set())
    assert res["cut_duration"] == pytest.approx(0.22 + 1 + 0.20 + 1 + 0.34, abs=0.08)
