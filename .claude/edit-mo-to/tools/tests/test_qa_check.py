import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
import qa_check as qc

PROBE = lambda p: {"duration": 10.0, "width": 1080, "height": 1920, "fps": 30, "rotation": 0}
QUIET = lambda p, t, **k: True


def _clip(file, src_in, at, length, **kw):
    return {"file": file, "src_in": src_in, "src_out": round(src_in + length, 10), "at": at, "track": "video_main",
            "speed": 1.0, "scale": 1.0, "x": 0.0, "y": 0.0, "mute": True, "transition": None, "effect": None, **kw}


def _plan(timelines=None, **kw):
    tl = {"name": "A", "vo": "/v/vo.mp3", "vo_in": 1.0, "vo_out": 5.0, "vo_volume": 1.0,
          "music": "/v/m.mp3", "music_volume": 0.1,
          "clips": [_clip("/v/a.mp4", 0.0, 0.0, 1.5), _clip("/v/b.mp4", 0.0, 1.5, 1.5), _clip("/v/c.mp4", 0.0, 3.0, 1.0)],
          "overlays": [{"template": "badge", "vars": {}, "at": 1.5, "duration": 1.0, "track": "ui", "sfx": "none"}],
          "texts": [], "manual": []}
    return {"project": "P", "fps": 30, "width": 1080, "height": 1920, "timelines": timelines or [tl], **kw}


def _seg(track, source, at, dur, src_in=0.0, **kw):
    kind = "audio" if track in ("vo", "music") or track.startswith("sfx") else "video"
    return {"track": track, "track_type": kind, "material_type": "videos", "source": source, "path": source,
            "remote_url": None, "size": "1080x1920" if kind == "video" else None, "text": None,
            "at": at, "duration": dur, "src_in": src_in, "speed": 1.0, "volume": 0.0 if kind == "video" else 1.0,
            "transform": {"x": 0.0, "y": 0.0}, "scale": {"x": 1.0, "y": 1.0}, "rotation": 0.0, "crop": None,
            "mask": [], **kw}


def _dump(name="A"):
    return {"timeline": name, "duration": 4.0, "segments": [
        _seg("video", "/v/a.mp4", 0.0, 1.5), _seg("video", "/v/b.mp4", 1.5, 1.5), _seg("video", "/v/c.mp4", 3.0, 1.0),
        _seg("overlay_ui", "/m/badge.mov", 1.5, 1.0, volume=None),
        _seg("vo", "/v/vo.mp3", 0.0, 4.0, 1.0), _seg("music", "/v/m.mp3", 0.0, 4.0, volume=0.1)]}


PLAN = _plan()
DUMP_OK = {"A": _dump()}
LIMITS = {"min_s": 3, "max_s": 60}


def _run(plan=PLAN, dumps=DUMP_OK, **kw):
    kw.setdefault("limits", LIMITS)
    return qc.check_build(plan, Path("/p"), segments_fn=lambda p, n, s: copy.deepcopy(dumps[n]),
                          probe=kw.pop("probe", PROBE), silent=kw.pop("silent", QUIET), **kw)


def _checks(r):
    return {row["check"] for row in r["rows"]}


def test_clean_build_passes():
    r = _run()
    assert r["rows"] == [] and r["verdict"] == "PASS" and r["passed"] >= 10


def test_missing_and_shifted_clips_fail():
    d = _dump()
    d["segments"][1]["at"] = 1.5 + 3 / 30                          # clip 2, three frames late
    d["segments"].append(_seg("video", "/v/zzz.mp4", 5.0, 1.0))   # nobody planned this
    r = _run(dumps={"A": d})
    present = [x for x in r["rows"] if x["check"] == "present"]
    assert len(present) == 1 and "0:03 late" in present[0]["evidence"] and r["verdict"].startswith("FAIL")
    assert [x["check"] for x in r["rows"] if x["check"] == "extras"] == ["extras"]
    assert all(x["status"] == "FAIL" and x["timeline"] == "A" for x in r["rows"])
    d2 = _dump()
    del d2["segments"][2]                                          # clip 3 gone
    row = next(x for x in _run(dumps={"A": d2})["rows"] if x["check"] == "present")
    assert "c.mp4" in row["evidence"] and "missing" in row["evidence"]


def test_placeholder_source_is_a_fail_not_a_crash():
    d = _dump()
    d["segments"][0]["source"] = "##_draftpath_placeholder_x_##/assets/video/a.mp4"
    r = _run(dumps={"A": d})
    unk = [x for x in r["rows"] if x["check"] == "unknown_source"]
    assert len(unk) == 1 and unk[0]["status"] == "FAIL" and "a.mp4" in unk[0]["evidence"]


def test_caption_track_and_reuse_across_timelines():
    d = _dump()
    d["segments"].append(_seg("captions", None, 0.0, 1.0, text="hello"))
    cap = [x for x in _run(dumps={"A": d})["rows"] if x["check"] == "captions"]
    assert len(cap) == 1 and cap[0]["status"] == "FAIL"
    t2 = copy.deepcopy(PLAN["timelines"][0])
    t2["name"] = "B"
    t2["clips"] = [_clip("/v/a.mp4", 0.5, 0.0, 1.5)]               # overlaps a.mp4 0-1.5 of timeline A
    t2["overlays"], t2["vo"], t2["music"] = [], None, None
    dB = {"timeline": "B", "duration": 1.5, "segments": [_seg("video", "/v/a.mp4", 0.0, 1.5, 0.5)]}
    plan = _plan([PLAN["timelines"][0], t2])
    r = _run(plan=plan, dumps={"A": _dump(), "B": dB}, limits=None)
    assert [x["check"] for x in r["rows"] if x["check"] == "reuse"] == ["reuse"]
    t2["clips"][0]["shared"] = True
    assert "reuse" not in _checks(_run(plan=_plan([PLAN["timelines"][0], t2]), dumps={"A": _dump(), "B": dB}, limits=None))


def test_delta_limits_rows_and_marks_verdict():
    d = _dump()
    d["segments"][1]["at"] = 1.5 + 5 / 30                           # clip 2 late: a neighbour of changed clip 3
    d["segments"].append(_seg("captions", None, 0.0, 1.0, text="x"))   # outside delta
    d["duration"] = 400                                              # outside delta
    r = _run(dumps={"A": d}, changed=["3"])
    assert r["verdict"].startswith("DELTA") and r["rows"]
    assert all(row["check"] in {"present", "extras", "overlay_on_cut", "reuse", "vo_span"} for row in r["rows"])
    d3 = _dump()
    d3["segments"][0]["at"] = 0.5                                    # clip 1: not a neighbour of clip 3
    r = _run(dumps={"A": d3}, changed=["3"])
    assert r["rows"] == [] and r["verdict"] == "DELTA PASS"


def test_rotation_and_dead_stretch_are_open():
    rot = lambda p: {**PROBE(p), "width": 3840, "height": 2160, "rotation": 90} if p.endswith("a.mp4") else PROBE(p)
    d = _dump()
    d["segments"][0]["size"] = "3840x2160"
    r = _run(dumps={"A": d}, probe=rot)
    row = next(x for x in r["rows"] if x["check"] == "rotation")
    assert row["status"] == "OPEN" and "2160x3840" in row["evidence"]
    d["segments"][0]["size"] = "2160x3840"
    assert "rotation" not in _checks(_run(dumps={"A": d}, probe=rot))
    plan = _plan([{**PLAN["timelines"][0], "clips": [_clip("/v/a.mp4", 0.0, 0.0, 3.0)], "overlays": [], "music": None}])
    dd = {"A": {"timeline": "A", "duration": 3.0,
                "segments": [_seg("video", "/v/a.mp4", 0.0, 3.0), _seg("vo", "/v/vo.mp3", 0.0, 4.0, 1.0)]}}
    r = _run(plan=plan, dumps=dd, limits=None)
    dead = next(x for x in r["rows"] if x["check"] == "dead_stretch")
    assert dead["status"] == "OPEN" and "0:00" in dead["evidence"]
    assert r["verdict"] == "PASS"       # OPEN rows never count toward the verdict


def test_talking_head_over_five_seconds_without_cover_fails():
    plan = _plan([{**PLAN["timelines"][0], "vo_out": 7.0, "clips": [_clip("/v/a.mp4", 0.0, 0.0, 6.0)], "overlays": []}])
    dd = {"A": {"timeline": "A", "duration": 6.0,
                "segments": [_seg("video", "/v/a.mp4", 0.0, 6.0), _seg("vo", "/v/vo.mp3", 0.0, 6.0, 1.0)]}}
    r = _run(plan=plan, dumps=dd, limits=None)
    assert any(x["check"] == "talking_head_5s" and x["status"] == "FAIL" for x in r["rows"])
    dd["A"]["segments"].append(_seg("video_overlay", "/v/b.mp4", 2.0, 1.0))
    assert "talking_head_5s" not in _checks(_run(plan=plan, dumps=dd, limits=None))


def test_tracks_volumes_and_layout():
    d = _dump()
    d["segments"][0]["volume"] = 1.0
    d["segments"][2]["track"] = "video_top"
    assert sum(x["check"] == "tracks_volumes" for x in _run(dumps={"A": d})["rows"]) >= 2
    clips = [_clip("/v/a.mp4", 0.0, 0.0, 1.5, track="video_top", layout="split-top", y=0.5)]
    plan = _plan([{**PLAN["timelines"][0], "clips": clips, "overlays": []}])
    seg = _seg("video_top", "/v/a.mp4", 0.0, 1.5)
    seg["transform"] = {"x": 0.0, "y": 0.5}
    dd = {"A": {"timeline": "A", "duration": 1.5, "segments": [seg]}}
    assert any(x["check"] == "layout" and "mask" in x["evidence"] for x in _run(plan=plan, dumps=dd, limits=None)["rows"])
    seg["mask"] = [{"name": "Rectangle", "config": {}}]
    assert "layout" not in _checks(_run(plan=plan, dumps=dd, limits=None))


def test_vo_span_and_edges():
    d = _dump()
    d["segments"][4]["src_in"] = 0.0
    d["segments"][4]["duration"] = 3.0
    assert sum(x["check"] == "vo_span" for x in _run(dumps={"A": d})["rows"]) >= 1
    noisy = lambda p, t, **k: False
    rows = [x for x in _run(silent=noisy)["rows"] if x["check"] == "vo_span"]
    assert {"vo_in", "vo_out"} <= {w for x in rows for w in ("vo_in", "vo_out") if w in x["evidence"]}
    plan = _plan([{**PLAN["timelines"][0], "vo_in": 0.0, "vo_out": 4.0}])
    d = _dump()
    d["segments"][4]["src_in"] = 0.0
    ev = " ".join(x["evidence"] for x in _run(plan=plan, dumps={"A": d}, silent=noisy)["rows"])
    assert "vo_in" not in ev and "vo_out" in ev


def test_overlay_off_cut_music_sfx_duration_canvas():
    plan = copy.deepcopy(PLAN)
    plan["timelines"][0]["overlays"][0]["at"] = 2.0
    d = _dump()
    d["segments"][3]["at"] = 2.0
    assert any(x["check"] == "overlay_on_cut" and x["status"] == "FAIL" for x in _run(plan=plan, dumps={"A": d})["rows"])
    plan["timelines"][0]["overlays"][0]["on"] = "word"
    rows = [x for x in _run(plan=plan, dumps={"A": d})["rows"] if x["check"] == "overlay_on_cut"]
    assert rows and all(x["status"] == "OPEN" for x in rows)
    loud = copy.deepcopy(PLAN)
    loud["timelines"][0]["music_volume"] = 0.6
    assert any(x["check"] == "music_level" and x["status"] == "OPEN" for x in _run(plan=loud)["rows"])
    assert "music_level" not in _checks(_run(plan={**loud, "style": "product-ad"}))
    d = _dump()
    d["duration"] = 90.0
    assert any(x["check"] == "duration" for x in _run(dumps={"A": d})["rows"])
    d = _dump()
    for i in range(4):
        d["segments"].append(_seg("sfx_a", "/s/whoosh.mp3", i * 0.5, 0.3))
    assert any(x["check"] == "sfx_repeat" for x in _run(dumps={"A": d})["rows"])
    assert any(x["check"] == "canvas" for x in _run(plan={**PLAN, "width": 1920, "height": 1080})["rows"])


def test_cli_prompts_prints_the_dict(tmp_path, capsys):
    spec = tmp_path / "p.json"
    spec.write_text(json.dumps({"style": "nope", "prompts": []}))
    with pytest.raises(SystemExit) as e:
        qc.main(["prompts", str(spec)])
    assert e.value.code == 1
    out = json.loads(capsys.readouterr().out)
    assert out["rows"][0]["check"] == "prompts" and out["verdict"].startswith("FAIL")


def _api_up():
    import requests
    try:
        requests.post("http://localhost:9001/create_draft", json={"width": 1080, "height": 1920}, timeout=3)
        return True
    except requests.RequestException:
        return False


def test_layout_units_match_a_real_vectcut_draft(monkeypatch):
    """x/y/scale in the plan -> VectCutAPI draft -> capcut_project.segments -> check_build `layout`, no conversion."""
    import shutil
    import subprocess
    import time
    import build_project as bp
    import capcut_project as cp
    from machine import PATHS, TMP
    if not _api_up():
        pytest.skip("VectCutAPI not running on :9001")
    monkeypatch.setattr(cp, "_capcut_running", lambda: False)
    src = TMP / "_test_fixture" / "qa_check" / "layout.mp4"
    if not src.exists():
        src.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "testsrc2=size=1080x1920:rate=30:duration=6", "-pix_fmt", "yuv420p", str(src)], check=True)
    f = src.as_posix()
    name = f"_test_qa_layout_{time.strftime('%Y%m%d-%H%M%S')}"
    tl = {"name": "L", "vo": None, "vo_in": 0.0, "vo_out": 2.0, "vo_volume": 1.0, "music": None, "music_volume": 0.1,
          "clips": [_clip(f, 0.0, 0.0, 2.0, x=0.25, scale=1.2),
                    _clip(f, 3.0, 0.0, 2.0, track="video_top", layout="split-top", y=0.5)],
          "overlays": [], "texts": [], "manual": []}
    plan = _plan([tl], project=name)
    made = None
    project = Path(PATHS["capcut_drafts"]) / name
    try:
        draft = bp.build_timeline(plan, tl, render=False)["draft"]
        made = Path(draft)
        cp.compose(project, [("L", Path(draft))])
        dump = cp.segments(project, "L", [src.parent])
        main_seg = next(s for s in dump["segments"] if s["track"] == "video")
        split = next(s for s in dump["segments"] if s["track"] == "video_top")
        assert (main_seg["transform"]["x"], main_seg["scale"]["x"]) == pytest.approx((0.25, 1.2), abs=0.01)
        assert split["transform"]["y"] == pytest.approx(0.5, abs=0.01) and split["mask"]
        r = qc.check_build(plan, project, segments_fn=lambda p, n, s: dump, probe=PROBE, silent=QUIET,
                           limits={})
        assert not [x for x in r["rows"] if x["check"] == "layout"], r["rows"]
    finally:
        if project.exists() and project.name.startswith("_test_"):
            shutil.rmtree(project, ignore_errors=True)
        if made and made.exists() and made.parent.name == Path(bp.BUILD).name:
            shutil.rmtree(made, ignore_errors=True)


def test_unknown_timelines_name_is_an_error_not_a_pass():
    with pytest.raises(ValueError, match="B"):
        _run(timelines=["B"])


def test_timeline_missing_from_the_project_is_a_fail_row():
    def segs(p, n, s):
        raise KeyError(f"no timeline named {n!r} in P; have ['A renamed']")
    r = qc.check_build(PLAN, Path("/p"), segments_fn=segs, probe=PROBE, silent=QUIET, limits=LIMITS)
    assert r["verdict"].startswith("FAIL") and any("not in the project" in row["evidence"] for row in r["rows"])


def test_search_stops_at_the_next_option(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(qc, "check_build", lambda plan, project, tls, changed, limits, search=(): seen.update(
        search=search, limits=limits) or {"rows": [], "passed": 1, "verdict": "PASS"})
    (tmp_path / "plan.json").write_text(json.dumps(PLAN), encoding="utf-8")
    (tmp_path / "limits.json").write_text(json.dumps(LIMITS), encoding="utf-8")
    qc.main(["build", str(tmp_path / "plan.json"), "/p", "--search", "/c1", "/c2", "--limits", str(tmp_path / "limits.json")])
    assert seen["search"] == ["/c1", "/c2"] and seen["limits"] == LIMITS


def test_square_job_canvas_follows_limits_ratio():
    square = {**PLAN, "width": 1080, "height": 1080}
    assert "canvas" not in _checks(_run(plan=square, limits={**LIMITS, "ratio": "1:1"}))
    assert "canvas" in _checks(_run(plan=PLAN, limits={**LIMITS, "ratio": "1:1"}))
    assert "canvas" in _checks(_run(plan=square))   # no ratio in limits: the 9:16 default


def test_expanded_product_ad_plan_keeps_music_level_quiet():
    import plan_tools as pt
    p = pt.expand({"project": "P", "style": "product-ad", "timelines": []})
    loud = copy.deepcopy(PLAN)
    loud["timelines"][0]["music_volume"] = 0.8
    assert p["style"] == "product-ad"
    assert "music_level" not in _checks(_run(plan={**loud, "style": p["style"]}))


def test_cutout_segment_matches_its_planned_overlay():
    plan = copy.deepcopy(PLAN)
    plan["timelines"][0]["overlays"][0].update(cutout=True, cutout_file="//?/D:/m/a_cutout_30f.mov", file="D:/m/big.mov")
    d = _dump()
    d["segments"].append(_seg("overlay_cutout", "D:/m/a_cutout_30f.mov", 1.5, 1.0, volume=0.0))
    r = _run(plan=plan, dumps={"A": d})
    assert "extras" not in _checks(r) and r["verdict"] == "PASS"
    d = _dump()   # the cutout missing from the timeline is a present FAIL
    assert any("cutout" in x["evidence"] for x in _run(plan=plan, dumps={"A": d})["rows"] if x["check"] == "present")


# --- captions ---

def _text_seg(track, text, at, dur, y=-0.62):
    return _seg(track, None, at, dur, text=text, track_type="text", material_type="texts", transform={"x": 0.0, "y": y})


ASR = [{"word": w, "start": s, "end": e} for w, s, e in [("hello", 1.0, 1.4), ("big", 1.5, 1.9), ("world", 2.0, 2.5)]]


def _cap_dump(*texts, extra=()):
    return {"timeline": "A", "duration": 4.0, "segments": [_seg("vo", "/v/vo.mp3", 0.0, 4.0, 1.0), *texts, *extra]}


def _cap_run(dump, script=("Hello big world.",), words=ASR, **kw):
    return qc.check_captions(_plan(), Path("/p"), "A", list(script), words, segments_fn=lambda p, n, s: copy.deepcopy(dump), **kw)


def test_temp_en_is_open_not_caption_fail():
    d = _dump()
    d["segments"].append(_text_seg("TEMP_EN_delete_me", "Hello", 0.0, 1.0, y=0.85))
    rows = _run(dumps={"A": d})["rows"]
    assert not [r for r in rows if r["check"] == "captions"]
    te = [r for r in rows if r["check"] == "temp_en"]
    assert len(te) == 1 and te[0]["status"] == "OPEN" and "delete before export" in te[0]["evidence"]
    assert "FAIL" not in _run(dumps={"A": d})["verdict"]


def test_captions_words_match_script():
    d = _cap_dump(_text_seg("captions", "Hello big", 0.0, 0.9), _text_seg("captions", "WORLD!", 1.0, 0.5))
    r = _cap_run(d)
    assert r["rows"] == [] and r["verdict"] == "PASS"


def test_captions_wrong_word_fails():
    d = _cap_dump(_text_seg("captions", "Hello small", 0.0, 0.9), _text_seg("captions", "world", 1.0, 0.5))
    r = _cap_run(d)
    row = [x for x in r["rows"] if x["check"] == "caption_words"]
    assert len(row) == 1 and row[0]["status"] == "FAIL" and "big -> small" in row[0]["evidence"]
    assert r["verdict"].startswith("FAIL")


def test_captions_out_of_sync_fails():
    d = _cap_dump(_text_seg("captions", "Hello big", 0.0, 0.9), _text_seg("captions", "world", 2.0, 0.5))
    rows = [x for x in _cap_run(d)["rows"] if x["check"] == "caption_sync"]
    assert len(rows) == 1 and rows[0]["status"] == "FAIL"


def test_captions_dropped_words_are_open():
    d = _cap_dump(_text_seg("captions", "Hello big world", 0.0, 1.5))
    r = _cap_run(d, script=("Hello big world. Bye now.",))
    row = [x for x in r["rows"] if x["check"] == "caption_words"]
    assert len(row) == 1 and row[0]["status"] == "OPEN" and "bye" in row[0]["evidence"].lower()
    assert r["verdict"] == "PASS"


def test_captions_band_and_gaps():
    d = _cap_dump(_text_seg("captions", "Hello big", 0.0, 0.9, y=0.0), _text_seg("captions", "world", 1.0, 0.5, y=0.0))
    assert [x["status"] for x in _cap_run(d)["rows"] if x["check"] == "caption_band"] == ["FAIL"]
    assert not [x for x in _cap_run(d, limits={"caption_band_px": 1000})["rows"] if x["check"] == "caption_band"]
    gappy = [{"word": w, "start": s, "end": e} for w, s, e in [("hello", 1.0, 1.4), ("big", 2.5, 2.9), ("world", 3.0, 3.5)]]
    d = _cap_dump(_text_seg("captions", "Hello", 0.0, 0.4), _text_seg("captions", "world", 2.0, 0.5))
    gaps = [x for x in _cap_run(d, words=gappy)["rows"] if x["check"] == "caption_gaps"]
    assert len(gaps) == 1 and gaps[0]["status"] == "OPEN"
