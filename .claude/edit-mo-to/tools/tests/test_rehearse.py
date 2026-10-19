import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import plan_build as pb  # noqa: E402
import rehearse as rh  # noqa: E402


def _w(spec):
    return [{"word": w, "start": s, "end": e} for w, s, e in spec]


def test_window_prefers_sentences_that_end_near_ten_seconds():
    words = _w([("Hi.", 0.2, 0.5), ("Short", 1.0, 1.3), ("one.", 1.4, 1.8),
                ("This", 3.0, 3.3), ("sentence", 3.4, 4.0), ("runs", 6.0, 6.4), ("long.", 12.4, 12.8),
                ("End", 13.0, 13.3), ("here.", 13.4, 13.8)])
    a, b = rh.pick_window(words, 20.0, 10.0)
    assert a == round(2.9 * 30) / 30          # starts on "This", a breath early
    assert abs((b - a) - 10.0) < 1.0 and b > 12.8  # ends just after "long." (a finished sentence)


def test_window_respects_start_and_stays_inside():
    words = _w([("a", 0.0, 0.4), ("b.", 5.0, 5.4), ("c", 9.0, 9.4)])
    a, b = rh.pick_window(words, 9.6, 10.0, start=0.0)
    assert a == 0.0 and b <= 9.6


def test_window_segs_are_frame_exact_and_rebased():
    keep = [{"src_in": 0.0, "src_out": 4.0, "at": 0.0}, {"src_in": 5.0, "src_out": 12.0, "at": 4.0}]
    segs = rh.window_segs(keep, 2.0, 8.0)
    assert segs[0] == {"src_in": 2.0, "from": 0, "to": 60}
    assert segs[1]["src_in"] == 5.0 and segs[1]["from"] == 60 and segs[1]["to"] == 180


def test_check_plan_catches_track_overlap_and_seg_gaps():
    plan = {"tracks": {"ui": 5}, "segs": [["a.mp4", 0, 0, 30, 1], ["a.mp4", 1, 31, 60, 1]],
            "overlays": [{"template": "a", "track": "ui", "from": 0, "to": 40},
                         {"template": "b", "track": "ui", "from": 30, "to": 50},
                         {"template": "c", "track": "title", "from": 0, "to": 10}]}
    errs = pb.check_plan(plan)
    assert any("overlaps" in e for e in errs)
    assert any("no index" in e for e in errs)
    assert any("gap" in e for e in errs)


def test_a_word_cut_at_the_limit_never_counts_as_a_sentence_end():
    # "day" runs past 10 s: a window ending there is mid-sentence, so the shorter clean sentence wins
    words = _w([("My", 0.0, 0.3), ("story.", 0.4, 0.9), ("Six", 1.0, 1.2), ("months", 1.3, 1.6), ("ago.", 1.7, 9.0),
                ("Now", 9.2, 9.5), ("a", 9.6, 9.9), ("day", 9.96, 10.18)])
    a, b = rh.pick_window(words, 30.0, 10.0)
    assert b <= 9.2  # ends after "ago.", never inside "day"
