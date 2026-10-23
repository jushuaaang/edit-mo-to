import subprocess
import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
import plan_tools as pt

PROBE = lambda p: {"duration": 10.0, "width": 1080, "height": 1920, "fps": 30, "rotation": 0}
QUIET = lambda p, t, **k: True


def _p2(timelines, **kw):
    base = {"project": "T", "fps": 30, "width": 1080, "height": 1920, "base": "/v/",
            "brand": {}, "vo": None, "music": None, "blocks": {}, "timelines": timelines}
    return pt.expand({**base, **kw})


def _tl(name="A", clips=(), overlays=(), **kw):
    return {"name": name, "seq": [{"clips": list(clips), "overlays": list(overlays)}], **kw}


PLAN_OK = _p2([_tl(clips=[["a.mp4", 0, 0, 60], ["b.mp4", 0, 60, 60]],
                   overlays=[["badge", 60, 30, {"text": "X", "top": 300}, "ui", "none"]])])
PLAN_REUSE = _p2([_tl("A", clips=[["a.mp4", 0, 0, 60], ["a.mp4", 30, 60, 60]]),
                  _tl("B", clips=[["a.mp4", 0, 0, 60]])])
PLAN_VO_LONG = _p2([_tl(clips=[["a.mp4", 0, 0, 150]], vo_in_f=30, vo_out_f=150)], vo={"file": "vo.mp3"})
PLAN_OVERLAYS = _p2([_tl(clips=[["a.mp4", 0, 0, 60], ["b.mp4", 0, 60, 60]], overlays=[
    ["badge", 45, 20, {"text": "X"}, "ui", "none"],
    ["bagde", 0, 20, {}, "ui2", "none"],
    ["badge", 0, 20, {"text": "Y", "top": 1700}, "ui3", "none"]])])
PLAN_SHARED = _p2([_tl("A", clips=[["h.mp4", 0, 0, 60, {"shared": True}]],
                       overlays=[["badge", 45, 20, {"text": "X"}, "ui", "none", {"on": "word"}]]),
                   _tl("B", clips=[["h.mp4", 0, 0, 60, {"shared": True}]])])


def _scale(s, **o):
    return _p2([_tl(clips=[["a.mp4", 0, 0, 60, {"scale": s, **o}]])])


def test_clean_plan_has_no_errors(): assert pt.check(PLAN_OK, probe=PROBE, silent=QUIET) == []


def test_reuse_within_and_across_timelines_is_reported():
    errs = pt.check(PLAN_REUSE, probe=PROBE, silent=QUIET)
    assert any("reused" in e and "T1 clip 2" in e for e in errs)
    assert any("overlaps T1 clip 1" in e and e.startswith("T2 clip 1") for e in errs)


def test_block_rows_are_exempt_from_cross_timeline_reuse():
    plan = _p2([_tl("A", clips=[["s.mp4", 0, 0, 60]]), _tl("B", clips=[["s.mp4", 0, 0, 60]])])
    assert any("overlaps" in e for e in pt.check(plan, probe=PROBE, silent=QUIET))
    for t in plan["timelines"]:
        t["clips"][0]["block"] = "BODY"
    assert pt.check(plan, probe=PROBE, silent=QUIET) == []


def test_vo_past_end_and_loud_edge_are_reported():
    errs = pt.check(PLAN_VO_LONG, probe=lambda p: {**PROBE(p), "duration": 3.0}, silent=lambda p, t, **k: False)
    assert any("vo_out 5.0 is past the file end 3.0" in e for e in errs) and any("not silent" in e for e in errs)


def test_overlay_off_cut_and_unknown_template_and_band():
    errs = pt.check(PLAN_OVERLAYS, probe=PROBE, silent=QUIET)
    assert any("does not start on a cut" in e for e in errs)
    assert any("no template 'bagde'" in e for e in errs)
    assert any("caption band" in e for e in errs)


def test_shared_aroll_and_word_overlays_are_allowed():
    assert pt.check(PLAN_SHARED, probe=PROBE, silent=QUIET) == []


def test_scale_convention_with_small_source():
    small = lambda p: {**PROBE(p), "width": 576, "height": 1024}
    assert pt.check(_scale(1.1), probe=small, silent=QUIET) == []
    assert any("black edges" in e for e in pt.check(_scale(0.8), probe=small, silent=QUIET))
    assert any("above 2.0" in e for e in pt.check(_scale(2.5), probe=small, silent=QUIET))
    assert pt.check(_scale(2.5, allow_scale=True), probe=small, silent=QUIET) == []


def test_rotated_source_uses_upright_size():
    rot = lambda p: {**PROBE(p), "width": 1920, "height": 1080, "rotation": 90}
    assert pt.check(_scale(1.0), probe=rot, silent=QUIET) == []


def test_gap_overlap_range_sfx_limits_and_texts():
    plan = _p2([_tl(clips=[["a.mp4", 0, 0, 60], ["b.mp4", 0, 70, 60], ["c.mp4", 400, 120, 60]],
                    overlays=[["badge", 70, 10, {"text": "X"}, "ui", [{"name": "nope"}]]])])
    plan["timelines"][0]["texts"] = [{"role": "caption", "text": "hi"}]
    errs = pt.check(plan, {"min_s": 1, "max_s": 3, "no_text": True}, probe=PROBE, silent=QUIET)
    for s in ("gap", "past the file end", "sfx 'nope'", "above the maximum", "no text", "caption"):
        assert any(s in e for e in errs), s


def test_unwhole_frame_is_reported():
    plan = _p2([_tl(clips=[["a.mp4", 0, 0, 60]])])
    plan["timelines"][0]["clips"][0]["at"] = 0.01
    assert any("whole frame" in e for e in pt.check(plan, probe=PROBE, silent=QUIET))


def test_edge_silent_on_real_audio(tmp_path):
    wav = tmp_path / "v.wav"
    subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-f", "lavfi", "-i", "sine=f=440:r=44100",
                    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-filter_complex",
                    "[0:a]atrim=0:1[a];[1:a]atrim=0:1[b];[2:a]atrim=0:1[c];[a][b][c]concat=n=3:v=0:a=1",
                    str(wav)], check=True)
    assert pt.edge_silent(str(wav), 0.5) and not pt.edge_silent(str(wav), 1.5) and pt.edge_silent(str(wav), 2.5)


def test_nested_overlay_overlap_is_reported():
    ov = lambda at, ln: ["badge", at, ln, {"text": "X", "top": 300}, "ui", "none", {"on": "word"}]
    plan = _p2([_tl(clips=[["a.mp4", 0, 0, 150]], overlays=[ov(0, 100), ov(10, 10), ov(50, 10)])])
    errs = pt.check(plan, probe=PROBE, silent=QUIET)
    assert any(e.startswith("T1 overlay 2") for e in errs) and any(e.startswith("T1 overlay 3") for e in errs)


def test_nested_main_clip_overlap_is_reported():
    plan = _p2([_tl(clips=[["a.mp4", 0, 0, 100], ["b.mp4", 0, 10, 10, {"track": "main"}], ["c.mp4", 0, 50, 10]])])
    errs = pt.check(plan, probe=PROBE, silent=QUIET)
    assert any(e.startswith("T1 clip 2") and "overlaps" in e for e in errs)
    assert any(e.startswith("T1 clip 3") and "overlaps" in e for e in errs)


def test_sped_clip_with_fractional_source_length_is_clean():
    plan = _p2([_tl(clips=[["a.mp4", 0, 0, 60, {"speed": 0.9}], ["b.mp4", 0, 60, 61, {"speed": 0.9}],
                           ["c.mp4", 0, 121, 30]])])
    assert pt.check(plan, probe=PROBE, silent=QUIET) == []


def test_square_plan_uses_its_own_canvas():
    sq = lambda p: {**PROBE(p), "width": 1080, "height": 1080}
    plan = _p2([_tl(clips=[["a.mp4", 0, 0, 60]], overlays=[["badge", 0, 30, {"text": "X", "top": 300}, "ui", "none"]])],
               width=1080, height=1080)
    assert pt.check(plan, {"ratio": "1:1"}, probe=sq, silent=QUIET) == []
    # 9:16 source on a square canvas: fitted 608x1080, so scale 1.0 leaves black edges
    assert any("black edges" in e and "1080x1080" in e for e in pt.check(plan, probe=PROBE, silent=QUIET))
    # the caption band sits at the bottom of a square canvas: y 900 is inside it, y 300 is not
    low = _p2([_tl(clips=[["a.mp4", 0, 0, 60]], overlays=[["badge", 0, 30, {"text": "X", "top": 900}, "ui", "none"]])],
              width=1080, height=1080)
    assert any("caption band" in e for e in pt.check(low, probe=sq, silent=QUIET))
    assert any("ratio" in e for e in pt.check(plan, {"ratio": "9:16"}, probe=sq, silent=QUIET))


def test_cutout_overlay_must_sit_inside_one_main_clip():
    plan = _p2([_tl(clips=[["a.mp4", 0, 0, 60], ["b.mp4", 0, 60, 60]],
                    overlays=[["badge", 0, 30, {"text": "X", "top": 300}, "ui", "none", {"cutout": True}],
                              ["badge", 60, 30, {"text": "Y", "top": 300}, "title", "none"],
                              ["badge", 45, 30, {"text": "Z", "top": 300}, "flash", "none", {"cutout": True, "on": "word"}]])])
    errs = pt.check(plan, probe=PROBE, silent=QUIET)
    assert [e for e in errs if "cutout" in e] and all(e.startswith("T1 overlay 3") for e in errs if "cutout" in e)
