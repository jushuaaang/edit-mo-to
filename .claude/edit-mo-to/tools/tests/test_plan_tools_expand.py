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
    lines = t.splitlines()
    assert lines[0].startswith("| # | Timeline | At | Len | File") and lines[0].endswith(" |")
    assert lines[1] == "|" + "---|" * 10 and len(lines) == 3
    assert lines[2].startswith("| 1 | T01 | 0:00 | 3:17 |") and lines[2].endswith(" |")


def test_timeline_vo_and_music_override_the_top_level_ones():
    p = pt.expand(_p2(music={"file": "m.mp3", "volume": 0.2}, timelines=[
        {"name": "H1", "seq": [{"clips": [["a.mp4", 0, 0, 30]]}]},
        {"name": "H2", "vo": {"file": "H2.mp3", "volume": 0.9}, "music": None, "seq": [{"clips": [["b.mp4", 0, 0, 30]]}]}]))
    t1, t2 = p["timelines"]
    assert t1["vo"] == "/v/vo.mp3" and t1["music"] == "/v/m.mp3" and t1["music_volume"] == 0.2
    assert t2["vo"] == "/v/H2.mp3" and t2["vo_volume"] == 0.9 and t2["music"] is None


def test_text_rows_expand_and_shift_with_their_block():
    body = {"clips": [["b.mp4", 0, 0, 60]], "texts": [["SOFT", 0, 30, "word"], ["SHOP NOW", 30, 30, "cta", {"bg": "#123456"}]]}
    p = pt.expand(_p2(blocks={"BODY": body}, timelines=[
        {"name": "T", "seq": [{"clips": [["h.mp4", 0, 0, 45]], "texts": [["NEW", 0, 15, "badge"]]}, {"use": "BODY", "at_f": 45}]}]))
    tx = p["timelines"][0]["texts"]
    assert tx[0] == {"text": "NEW", "at": 0.0, "duration": 0.5, "style": "badge"}
    assert tx[1] == {"text": "SOFT", "at": 1.5, "duration": 1.0, "style": "word", "block": "BODY"}
    assert tx[2]["at"] == 2.5 and tx[2]["bg"] == "#123456" and tx[2]["style"] == "cta"
    with pytest.raises(ValueError, match="style"):
        pt.expand(_p2(timelines=[{"name": "T", "seq": [{"clips": [["a.mp4", 0, 0, 30]], "texts": [["X", 0, 30, "huge"]]}]}]))


def test_brand_fills_only_vars_whose_default_is_the_same_kind():
    # badge declares accent with an empty default and renders it as text: a colour there shows "#ff0000 NEW"
    p = pt.expand(_p2(timelines=[{"name": "T", "seq": [{"clips": [["a.mp4", 0, 0, 30]],
                                                        "overlays": [["badge", 0, 30, {"text": "NEW"}, "ui", "none"],
                                                                     ["glass-card-v2", 0, 30, {"title": "X"}, "title", "none"]]}]}]))
    badge, card = (o["vars"] for o in p["timelines"][0]["overlays"])
    assert "accent" not in badge and badge["bg"] == "#000000" and badge["fg"] == "#ffffff" and badge["font"] == "Inter"
    assert card["accent"] == "#ff0000" and card["font"] == "Inter"
    assert pt._brand_fits("accent", "#123", "rgba(8,12,30,0.86)") and not pt._brand_fits("font", "#fff", "Inter")
    assert not pt._brand_fits("font", "Inter", "#ffffff")


def test_expand_copies_temp_en():
    p = pt.expand(_p2(temp_en={"english": "script_en.txt", "timings": "C:/vo/vo.json"}, temp_en_removed=False,
                      captions_style={"font_size": 11},
                      timelines=[{"name": "T1", "seq": [{"clips": [["a.mp4", 0, 0, 30]]}]},
                                 {"name": "T2", "seq": [{"clips": [["a.mp4", 30, 0, 30]]}],
                                  "temp_en": {"english": "hook_en.txt", "timings": "hook.json"}}]))
    assert p["temp_en"] == {"english": "/v/script_en.txt", "timings": "C:/vo/vo.json"}
    assert p["temp_en_removed"] is False and p["captions_style"] == {"font_size": 11}
    assert "temp_en" not in p["timelines"][0]
    assert p["timelines"][1]["temp_en"] == {"english": "/v/hook_en.txt", "timings": "/v/hook.json"}
    assert "temp_en" not in pt.expand(_p2(timelines=[]))
