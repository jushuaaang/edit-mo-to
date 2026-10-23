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
