import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
import plan_tools as pt


def _p2(**kw):
    base = {"project": "T", "fps": 30, "width": 1080, "height": 1920, "base": "/v/",
            "brand": {"font": "Inter", "bg": "#000000", "fg": "#ffffff", "accent": "#ff0000"},
            "vo": {"file": "vo.mp3", "volume": 1.0}, "music": None, "blocks": {}, "timelines": []}
    return {**base, **kw}


def test_frames_become_ten_decimal_seconds_and_paths_join_base():
    p = pt.expand(_p2(timelines=[{"name": "T01", "seq": [{"clips": [["a.mp4", 7, 0, 107]]}]}]))
    c = p["timelines"][0]["clips"][0]
    assert c["file"] == "/v/a.mp4" and c["src_in"] == 0.2333333333 and c["src_out"] == 3.8
    assert c["at"] == 0.0 and c["track"] == "video_main" and c["mute"] is True and c["speed"] == 1.0
    assert p["timelines"][0]["vo"] == "/v/vo.mp3" and p["timelines"][0]["vo_out"] == 3.5666666667


def test_block_reuse_shifts_rows_and_is_written_once():
    body = {"clips": [["b.mp4", 0, 0, 30]], "overlays": [["badge", 0, 30, {"text": "X"}, "ui", "default"]]}
    p = pt.expand(_p2(blocks={"BODY": body}, timelines=[
        {"name": "H1", "seq": [{"clips": [["h1.mp4", 0, 0, 60]]}, {"use": "BODY", "at_f": 60}]},
        {"name": "H2", "seq": [{"clips": [["h2.mp4", 0, 0, 45]]}, {"use": "BODY", "at_f": 45}]}]))
    assert p["timelines"][0]["clips"][1]["at"] == 2.0 and p["timelines"][1]["clips"][1]["at"] == 1.5
    assert p["timelines"][0]["overlays"][0]["at"] == 2.0 and p["timelines"][0]["clips"][1]["block"] == "BODY"


def test_brand_fills_only_declared_vars_and_keyframes_convert():
    p = pt.expand(_p2(timelines=[{"name": "T", "seq": [{"clips": [["a.mp4", 0, 0, 30, {"kf": [[0, 1.0, 0, 0], [15, 1.2, 0.1, -0.1]], "transition": "Blur"}]],
                                                        "overlays": [["badge", 0, 30, {"text": "Y"}, "ui", "none"]]}]}]))
    ov = p["timelines"][0]["overlays"][0]; c = p["timelines"][0]["clips"][0]
    assert ov["vars"]["font"] == "Inter" and ov["vars"]["bg"] == "#000000" and "ring" not in ov["vars"]
    assert c["keyframes"] == [{"t": 0.0, "scale": 1.0, "x": 0, "y": 0}, {"t": 0.5, "scale": 1.2, "x": 0.1, "y": -0.1}]
    assert c["transition"] == "Blur" and c["transition_duration"] == 0.3


def test_unknown_track_and_fractional_frame_are_rejected():
    with pytest.raises(ValueError, match="track"):
        pt.expand(_p2(timelines=[{"name": "T", "seq": [{"clips": [["a.mp4", 0, 0, 30, {"track": "side"}]]}]}]))
    with pytest.raises(ValueError, match="whole frame"):
        pt.expand(_p2(timelines=[{"name": "T", "seq": [{"clips": [["a.mp4", 0, 0, 30.5]]}]}]))


def test_plan_table_has_one_row_per_clip_in_seconds_frames():
    p = pt.expand(_p2(timelines=[{"name": "T01", "seq": [{"clips": [["a.mp4", 7, 0, 107]]}]}]))
    t = pt.plan_table(p)
    assert t.splitlines()[0].startswith("# | Timeline | At | Len | File") and "| 0:00 | 3:17 |" in t
