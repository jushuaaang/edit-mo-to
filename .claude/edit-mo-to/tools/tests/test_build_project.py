import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_project as bp  # noqa: E402
import capcut_project as cp  # noqa: E402
from machine import PATHS, TMP  # noqa: E402

API = "http://localhost:9001"

CLIP = {"file": "/a.mp4", "src_in": 0.0, "src_out": 2.0, "at": 0.0, "speed": 1.0, "track": "video_main",
        "x": 0.0, "y": 0.0, "scale": 1.0, "mute": True}

PLAN = {"project": "_unit", "fps": 30, "width": 1080, "height": 1920, "base": "/video",
        "timelines": [{
            "name": "Timeline 01", "vo": "/vo.mp3", "vo_in": 1.5, "vo_out": 9.0, "vo_volume": 1.0,
            "music": "/music.mp3", "music_volume": 0.1, "manual": [],
            "clips": [{**CLIP, "file": "/a.mp4", "src_in": 0.0, "src_out": 2.0, "at": 0.0},
                      {**CLIP, "file": "/b.mp4", "src_in": 1.0, "src_out": 4.0, "at": 2.0, "mute": False,
                       "gain_db": -6.0, "transition": "Dissolve", "transition_duration": 0.3,
                       "keyframes": [{"t": 0.0, "scale": 1.0, "x": 0, "y": 0}, {"t": 1.0, "scale": 1.2, "x": 0, "y": 0}]},
                      {**CLIP, "file": "/c.mp4", "src_in": 0.0, "src_out": 2.0, "at": 2.0, "track": "video_top",
                       "layout": "split-top", "y": 0.5}],
            "overlays": [{"template": "badge", "vars": {"text": "NEW"}, "at": 0.0, "duration": 1.0, "track": "ui",
                          "sfx": "default", "file": "/ov1.mov"},
                         {"template": "cta", "vars": {}, "at": 3.0, "duration": 2.0, "track": "title",
                          "sfx": "none", "file": "/ov2.mov"}],
            "effects": [{"name": "White Flash", "at": 2.0, "duration": 0.2}],
            "texts": []}]}


def _post_recorder():
    calls = []

    def post(ep, body):
        calls.append((ep, body))
        return {"success": True, "output": {"draft_id": "dfd_test"}}
    return calls, post


def test_clip_body_exact_microseconds_and_main_track_name():
    b = bp.clip_body("d", {"file": "/a.mp4", "src_in": 0.2333333333, "src_out": 3.8, "at": 1.0333333333, "speed": 1.0,
                           "track": "video_main", "x": 0, "y": 0, "scale": 1.0, "mute": True}, (1080, 1920))
    assert b["track_name"] == "video" and b["relative_index"] == 0 and b["volume"] == 0
    assert round(b["target_start"] * 1e6) == 1033333 and round((b["end"] - b["start"]) * 1e6) == 3566667


def test_split_top_gets_mask_and_half_offset():
    b = bp.clip_body("d", {**CLIP, "track": "video_top", "layout": "split-top", "y": 0.5}, (1080, 1920))
    assert b["mask_type"] == "Rectangle" and b["mask_size"] == 0.5 and b["mask_rect_width"] == 1.0 and b["transform_y"] == 0.5
    assert b["mask_center_x"] == 0 and b["mask_center_y"] == 0 and b["relative_index"] == 1


def test_clip_body_gain_and_transition():
    b = bp.clip_body("d", PLAN["timelines"][0]["clips"][1], (1080, 1920))
    assert b["volume"] == pytest.approx(10 ** (-6 / 20)) and b["transition"] == "Dissolve"
    assert b["transition_duration"] == 0.3
    assert "transition" not in bp.clip_body("d", CLIP, (1080, 1920))


def test_keyframes_nudge_first_point_and_use_timeline_seconds():
    kb = bp.keyframe_body("d", {**CLIP, "at": 2.0, "keyframes": [{"t": 0.0, "scale": 1.0, "x": 0, "y": 0}, {"t": 0.5, "scale": 1.2, "x": 0.1, "y": 0}]}, "video")
    # VectCutAPI's batch mode takes one (property, time, value) triple per entry, all three lists equally long;
    # grouped by property, so each property's points are in time order
    assert list(dict.fromkeys(kb["property_types"])) == ["uniform_scale", "position_x", "position_y"]
    assert len(kb["property_types"]) == len(kb["times"]) == len(kb["values"]) == 6
    assert kb["times"][0] == pytest.approx(2.001) and kb["times"][1] == 2.5
    assert kb["values"][:2] == ["1.0", "1.2"] and kb["values"][3] == "0.1" and kb["track_name"] == "video"
    assert bp.keyframe_body("d", CLIP, "video") is None


def test_effect_body_has_empty_params():
    b = bp.effect_body("d", {"name": "White Flash", "at": 2.1, "duration": 0.2})
    assert b["params"] == [] and b["effect_type"] == "White Flash" and b["track_name"] == "effect_01"
    assert b["start"] == 2.1 and round(b["end"] * 1e6) == 2300000


def test_build_timeline_order_and_vo_end_on_frame(tmp_path, monkeypatch):
    calls, post = _post_recorder()
    monkeypatch.setattr(bp.cp, "wait_for_draft", lambda p, t=30: Path(p))
    res = bp.build_timeline(PLAN, PLAN["timelines"][0], post=post, render=False)   # overlays carry prebuilt "file"
    eps = [e for e, _ in calls]
    assert eps[0] == "create_draft" and eps[1] == "add_video" and calls[1][1]["track_name"] != "video"   # overlay track first
    vo = next(b for e, b in calls if e == "add_audio" and b["track_name"] == "vo")
    assert vo["end"] == PLAN["timelines"][0]["vo_in"] + res["end_frame"] / 30 and eps[-1] == "save_draft"
    assert calls[-1][1]["auto_deploy"] is False
    assert res["end_frame"] == 150
    videos = [b for e, b in calls if e == "add_video"]
    assert [b["track_name"] for b in videos] == ["overlay_ui", "overlay_title", "video", "video", "video_top"]
    kf = eps.index("add_video_keyframe")
    assert eps.index("add_effect") > kf > max(i for i, e in enumerate(eps) if e == "add_video")
    assert eps.index("add_audio") > eps.index("add_effect")
    music = next(b for e, b in calls if e == "add_audio" and b["track_name"] == "music")
    assert music["end"] == 5.0 and music["volume"] == 0.1


def test_sfx_cues_come_from_plan_common(monkeypatch):
    # two overlays with sfx default -> add_audio bodies on sfx_a/sfx_b, none past the end
    calls, post = _post_recorder()
    monkeypatch.setattr(bp.cp, "wait_for_draft", lambda p, t=30: Path(p))
    tl = {**PLAN["timelines"][0], "effects": [], "clips": [{**CLIP, "src_out": 2.0}],
          "overlays": [{"template": "badge", "vars": {}, "at": 0.0, "duration": 1.0, "track": "ui",
                        "sfx": "default", "file": "/o1.mov"},
                       {"template": "badge", "vars": {}, "at": 0.2, "duration": 1.0, "track": "title",
                        "sfx": "default", "file": "/o2.mov"},
                       {"template": "badge", "vars": {}, "at": 1.9, "duration": 1.0, "track": "flash",
                        "sfx": "default", "file": "/o3.mov"}]}
    res = bp.build_timeline(PLAN, tl, post=post, render=False)
    sfx = [b for e, b in calls if e == "add_audio" and b["track_name"].startswith("sfx_")]
    assert {b["track_name"] for b in sfx} == {"sfx_a", "sfx_b"}
    assert all(round((b["target_start"] + b["end"] - b["start"]) * 1e6) <= round(res["end_frame"] * 1e6 / 30)
               for b in sfx)
    frames = bp.overlays_to_frames(tl)
    expected = bp.sfx_cues(frames, round(res["end_frame"] * 1e6 / 30))
    assert [round(b["target_start"] * 1e6) for b in sfx] == [c["at_us"] for c in expected]


def test_overlays_to_frames_converts_seconds():
    o = bp.overlays_to_frames(PLAN["timelines"][0])
    assert o[0]["from"] == 0 and o[0]["to"] == 30 and o[1]["from"] == 90 and o[1]["to"] == 150
    assert o[1]["track"] == "title" and o[0]["sfx"] == "default" and o[0]["file"] == "/ov1.mov"


def test_empty_draft_url_from_save_is_a_failure(monkeypatch):
    # VectCutAPI answers success with draft_url "" when the save crashed (seen with keyframes on Windows)
    def post(ep, body):
        return {"success": True, "output": {"draft_id": "dfd_test", "draft_url": "", "success": True}}
    monkeypatch.setattr(bp.cp, "wait_for_draft", lambda p, t=30: Path(p))
    with pytest.raises(bp.cp.DraftSaveFailed, match="keyframes"):
        bp.build_timeline(PLAN, PLAN["timelines"][0], post=post, render=False)


def test_build_stops_without_stop_iteration_patch(monkeypatch):
    monkeypatch.setattr(bp, "stop_iteration_patched", lambda path=None: False)
    with pytest.raises(RuntimeError, match="StopIteration patch"):
        bp.build({**PLAN, "timelines": [{**PLAN["timelines"][0], "overlays": []}]}, render=False)



def _stub_project(monkeypatch, made):
    import sheets
    monkeypatch.setattr(bp, "stop_iteration_patched", lambda path=None: True)
    monkeypatch.setattr(bp.cp, "wait_for_draft", lambda p, t=30: Path(p))
    monkeypatch.setattr(bp.cp, "compose", lambda project, pairs, link_originals=True:
                        {"project": str(project), "timelines": {n: "id" for n, _ in pairs}})
    monkeypatch.setattr(bp.cp, "import_media", lambda project, files: {"added": list(files), "missing": []})
    monkeypatch.setattr(bp.cp, "segments", lambda project, name, dirs=(): {"timeline": name, "segments": []})
    monkeypatch.setattr(sheets, "clip_sheets", lambda plan, tl, out: {"sheets": [{"path": str(out / "clips_1.png")}]})
    monkeypatch.setattr(sheets, "overlay_sheets", lambda plan, tl, out: made.append(tl) or
                        {"sheets": [{"path": str(out / "overlays_1.png")}]})


def _agent_plan(tmp_path):
    """PLAN as the agent's plan.json holds it (no overlay files yet), saved to tmp_path/plan.json."""
    plan = json.loads(json.dumps({**PLAN, "project": "_unit_build", "base": tmp_path.as_posix()}))
    for o in plan["timelines"][0]["overlays"]:
        o.pop("file")
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    return plan, plan_path


def test_build_writes_the_built_plan_per_timeline_and_overlay_sheets(tmp_path, monkeypatch):
    made = []
    _stub_project(monkeypatch, made)
    _, post = _post_recorder()
    plan, plan_path = _agent_plan(tmp_path)
    for n, o in enumerate(plan["timelines"][0]["overlays"], 1):   # prebuilt by an earlier render
        o["file"] = (tmp_path / f"ov{n}.mov").as_posix()
    res = bp.build(plan, job="_unit_build", post=post, render=False, plan_path=plan_path)
    built = json.loads(bp.built_plan_path(tmp_path, "Timeline 01").read_text(encoding="utf-8"))
    assert [t["name"] for t in built["timelines"]] == ["Timeline 01"]
    assert [o["file"] for o in built["timelines"][0]["overlays"]] == [(tmp_path / "ov1.mov").as_posix(),
                                                                     (tmp_path / "ov2.mov").as_posix()]
    assert "file" not in json.loads(plan_path.read_text(encoding="utf-8"))["timelines"][0]["overlays"][0]  # render False
    assert not list(tmp_path.rglob("*.tmp"))
    assert made == ["Timeline 01"] and any(p.endswith("overlays_1.png") for p in res["sheets"])


def test_build_with_render_writes_overlay_files_into_plan_json(tmp_path, monkeypatch):
    _stub_project(monkeypatch, [])
    _, post = _post_recorder()
    plan, plan_path = _agent_plan(tmp_path)

    def fake_render(p, tls):
        for n, o in enumerate(tls[0]["overlays"], 1):
            o["file"] = (tmp_path / f"r{n}.mov").as_posix()
        return {"rendered": 2, "jobs": 2, "cutouts": 0}
    monkeypatch.setattr(bp, "render_assets", fake_render)
    bp.build(plan, job="_unit_build", post=post, render=True, plan_path=plan_path)
    written = json.loads(plan_path.read_text(encoding="utf-8"))
    assert [o["file"] for o in written["timelines"][0]["overlays"]] == [(tmp_path / "r1.mov").as_posix(),
                                                                       (tmp_path / "r2.mov").as_posix()]


def test_ops_from_built_copy_to_revised_plan_and_mark_built(tmp_path, monkeypatch):
    import plan_tools as pt
    _stub_project(monkeypatch, [])
    _, post = _post_recorder()
    plan, plan_path = _agent_plan(tmp_path)
    for n, o in enumerate(plan["timelines"][0]["overlays"], 1):
        o["file"] = (tmp_path / f"ov{n}.mov").as_posix()
    bp.build(plan, job="_unit_build", post=post, render=False)
    old = json.loads(bp.built_plan_path(tmp_path, "Timeline 01").read_text(encoding="utf-8"))
    revised = json.loads(plan_path.read_text(encoding="utf-8"))          # re-expanded: no overlay files
    revised["timelines"][0]["clips"][0]["src_out"] = 1.5                  # clip 1: 2.0 s -> 1.5 s
    revised["timelines"][0]["overlays"][1]["vars"] = {"text": "BUY"}      # overlay 2 changed
    dump = {"segments": [{"id": "SEG_A", "track": "video", "source": "/a.mp4", "src_in": 0.0, "at": 0.0}]}
    r = pt.ops(old, revised, "Timeline 01", dump)
    assert r["ops"] == [{"op": "set", "id": "SEG_A", "duration": 1500000, "src_duration": 1500000}]
    m = bp.mark_built(revised, "Timeline 01")
    after = json.loads(Path(m["built_plan"]).read_text(encoding="utf-8"))["timelines"][0]["overlays"]
    assert after[0]["file"] == (tmp_path / "ov1.mov").as_posix() and "file" not in after[1]
    assert m["carried"] == 1 and m["unrendered"] == ["ov2 cta"]


# ---------- integration (real VectCutAPI) ----------

def _api_up():
    try:
        requests.post(f"{API}/create_draft", json={"width": 1080, "height": 1920}, timeout=3)
        return True
    except requests.RequestException:
        return False


def _synthetic(path: Path, pattern: str):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i",
                        f"{pattern}=size=1080x1920:rate=30:duration=6", "-f", "lavfi", "-i",
                        "sine=frequency=440:duration=6", "-shortest", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path.as_posix()


def test_build_two_timelines_end_to_end(monkeypatch):
    if not _api_up():
        pytest.skip("VectCutAPI not running on :9001")
    monkeypatch.setattr(cp, "_capcut_running", lambda: False)
    base = TMP / "_test_fixture" / "build_project"
    a = _synthetic(base / "clip_a.mp4", "testsrc2")
    b = _synthetic(base / "clip_b.mp4", "smptebars")
    vo = _synthetic(base / "vo.mp4", "testsrc")
    shutil.rmtree(base / ".edit-mo-to", ignore_errors=True)
    name = f"_test_build_{time.strftime('%Y%m%d-%H%M%S')}"
    clip = {**CLIP, "mute": True}
    plan = {"project": name, "fps": 30, "width": 1080, "height": 1920, "base": base.as_posix(),
            "timelines": [
                {"name": "Timeline 01", "vo": vo, "vo_in": 0.0, "vo_out": 4.0, "vo_volume": 1.0, "music": None,
                 "music_volume": 0.1, "manual": [], "texts": [],
                 "clips": [{**clip, "file": a, "src_in": 0.0, "src_out": 2.0, "at": 0.0},
                           {**clip, "file": b, "src_in": 1.0, "src_out": 3.0, "at": 2.0}],
                 "overlays": [{"template": "badge", "vars": {"text": "TEST"}, "at": 0.0, "duration": 1.0,
                               "track": "ui", "sfx": "default"}]},
                {"name": "Timeline 02", "vo": vo, "vo_in": 0.0, "vo_out": 2.0, "vo_volume": 1.0, "music": None,
                 "music_volume": 0.1, "manual": [], "texts": [],
                 "clips": [{**clip, "file": b, "src_in": 3.0, "src_out": 5.0, "at": 0.0}],
                 "overlays": [{"template": "badge", "vars": {"text": "TWO"}, "at": 0.0, "duration": 1.0,
                               "track": "ui", "sfx": "none"}]}]}
    project = Path(PATHS["capcut_drafts"]) / name
    job = name
    try:
        res = bp.build(plan, job=job)
        assert Path(res["project"]) == project
        names = [t["name"] for t in cp.list_timelines(project)]
        assert names == ["Timeline 01", "Timeline 02"]
        segs = cp.segments(project, "Timeline 01", [base])["segments"]
        assert len([s for s in segs if s["track_type"] == "video"]) == 2 + 1
        assert res["sheets"] and all(Path(p).exists() for p in res["sheets"])
        rows = [ln for ln in Path(res["report"]).read_text(encoding="utf-8").splitlines() if ln.startswith("Timeline 0")]
        assert len(rows) == 3
        assert (base / ".edit-mo-to" / "built" / "Timeline 01.json").exists()
        meta = json.loads((project / "draft_meta_info.json").read_text(encoding="utf-8"))
        listed = [v["file_Path"] for g in meta["draft_materials"] if g.get("type") == 0 for v in g["value"]]
        for src in (a, b, vo):
            assert listed.count(src) == 1 and Path(src).is_absolute()
    finally:
        if project.exists() and project.name.startswith("_test_"):
            shutil.rmtree(project, ignore_errors=True)


def test_text_body_styles_like_the_editor_presets():
    plan = {**PLAN, "brand": {"accent": "#0E2F5A"}}
    w = bp.text_body("d", {"text": "SOFT", "at": 1.0, "duration": 0.5, "style": "word"}, plan)
    assert w["text"] == "SOFT" and w["start"] == 1.0 and w["end"] == 1.5 and w["font_size"] == 14
    assert w["background_alpha"] == 0 and w["shadow_enabled"] is True and w["transform_y"] == 0 and w["bold"] is True
    b = bp.text_body("d", {"text": "NEW", "at": 0.0, "duration": 1.0, "style": "badge"}, plan)
    assert b["background_color"] == "#0E2F5A" and b["background_alpha"] == 1 and b["font_size"] == 10
    assert b["transform_y"] == 0.6 and b["background_round_radius"] == 0.3 and b["font_color"] == "#FFFFFF"
    c = bp.text_body("d", {"text": "SHOP", "at": 0.0, "duration": 1.0, "style": "cta", "bg": "#111111", "font": "Inter"},
                     {**PLAN})
    assert c["transform_y"] == -0.55 and c["background_color"] == "#111111" and c["font"] == "Inter"
    assert bp.text_body("d", {"text": "X", "at": 0, "duration": 1, "style": "badge"}, PLAN)["background_color"] == "#E53935"


def test_build_timeline_adds_texts_before_audio(monkeypatch):
    calls, post = _post_recorder()
    monkeypatch.setattr(bp.cp, "wait_for_draft", lambda p, t=30: Path(p))
    tl = {**PLAN["timelines"][0], "texts": [{"text": "SOFT", "at": 0.0, "duration": 1.0, "style": "word"}]}
    res = bp.build_timeline(PLAN, tl, post=post, render=False)
    eps = [e for e, _ in calls]
    assert eps.count("add_text") == 1 and eps.index("add_text") < eps.index("add_audio")
    assert res["counts"]["texts"] == 1


def test_overlay_only_draft_keeps_its_sfx(monkeypatch):
    # editor.md: motion overlays and their SFX go in a draft holding only them (no clips, no VO)
    calls, post = _post_recorder()
    monkeypatch.setattr(bp.cp, "wait_for_draft", lambda p, t=30: Path(p))
    tl = {"name": "ov", "vo": None, "music": None, "clips": [], "texts": [], "manual": [],
          "overlays": [{"template": "badge", "vars": {}, "at": 1.0, "duration": 1.0, "track": "ui",
                        "sfx": "default", "file": "/o1.mov"},
                       {"template": "badge", "vars": {}, "at": 4.0, "duration": 1.0, "track": "ui",
                        "sfx": "default", "file": "/o2.mov"}]}
    res = bp.build_timeline(PLAN, tl, post=post, render=False)
    sfx = [b for e, b in calls if e == "add_audio" and b["track_name"].startswith("sfx_")]
    want = bp.sfx_cues(bp.overlays_to_frames(tl))
    assert len(want) >= 2 and [round(b["target_start"] * 1e6) for b in sfx] == [c["at_us"] for c in want]
    assert res["end_frame"] == 150   # the last overlay's end


def test_music_end_s_overrides_the_plan_length_and_canvas_follows_the_plan(tmp_path, monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(bp, "music_draft", lambda end_f, music, volume, canvas=(1080, 1920): seen.update(
        end_f=end_f, canvas=canvas) or "/d")
    p = tmp_path / "plan.json"
    p.write_text(json.dumps({**PLAN, "width": 1080, "height": 1080}), encoding="utf-8")
    bp.main(["music", str(p), "Timeline 01", "--music", "/m.mp3", "--volume", "0.1"])
    assert seen == {"end_f": 150, "canvas": (1080, 1080)}
    bp.main(["music", str(p), "Timeline 01", "--music", "/m.mp3", "--volume", "0.1", "--end-s", "12.4"])
    assert seen["end_f"] == 372


def test_music_draft_uses_the_canvas(monkeypatch):
    calls, post = _post_recorder()
    monkeypatch.setattr(bp.cp, "wait_for_draft", lambda p, t=30: Path(p))
    bp.music_draft(372, "/m.mp3", 0.1, post=post, canvas=(1080, 1080))
    assert calls[0][1] == {"width": 1080, "height": 1080} and round(calls[1][1]["end"] * 1e6) == bp.US(372)


def test_render_assets_rerenders_an_existing_file_without_alpha_or_length(tmp_path, monkeypatch):
    plan = {"project": "_unit", "base": str(tmp_path), "timelines": [{"name": "T", "clips": [], "overlays": [
        {"template": "badge", "vars": {"text": "A"}, "at": 0.0, "duration": 1.0, "track": "ui", "sfx": "none"},
        {"template": "badge", "vars": {"text": "B"}, "at": 1.0, "duration": 1.0, "track": "ui", "sfx": "none"}]}]}
    rendered = []

    def fake_render(template, out, variables):
        rendered.append(variables["text"])
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_bytes(b"mov")
        return {"file": str(out)}
    bp.render_assets(plan, plan["timelines"], render_fn=fake_render)
    assert sorted(rendered) == ["A", "B"]
    for o in plan["timelines"][0]["overlays"]:
        del o["file"]
    good = {"alpha": True, "duration": 1.0}
    monkeypatch.setattr(bp.mr, "_probe", lambda p: good if "_01_" in Path(p).name else {"alpha": False, "duration": 1.0})
    rendered.clear()
    bp.render_assets(plan, plan["timelines"], render_fn=fake_render)
    assert rendered == ["B"]   # A reused, B (no alpha) rendered again
    monkeypatch.setattr(bp.mr, "_probe", lambda p: {"alpha": True, "duration": 0.0})
    for o in plan["timelines"][0]["overlays"]:
        del o["file"]
    rendered.clear()
    bp.render_assets(plan, plan["timelines"], render_fn=fake_render)
    assert sorted(rendered) == ["A", "B"]


def test_clip_effect_becomes_an_effect_over_the_clip(monkeypatch):
    calls, post = _post_recorder()
    monkeypatch.setattr(bp.cp, "wait_for_draft", lambda p, t=30: Path(p))
    tl = {**PLAN["timelines"][0], "effects": [], "overlays": [],
          "clips": [{**CLIP, "at": 0.0, "duration": 2.0}, {**CLIP, "file": "/b.mp4", "at": 2.0, "duration": 1.5,
                                                          "src_out": 1.5, "effect": "Shake"}]}
    res = bp.build_timeline(PLAN, tl, post=post, render=False)
    fx = [b for e, b in calls if e == "add_effect"]
    assert len(fx) == 1 and fx[0]["effect_type"] == "Shake" and fx[0]["params"] == []
    assert fx[0]["start"] == 2.0 and round(fx[0]["end"] * 1e6) == 3500000 and res["counts"]["effects"] == 1


def test_render_assets_writes_plain_paths_and_counts_copies(tmp_path):
    ovs = [{"template": "badge", "vars": {"text": t}, "at": float(i), "duration": 1.0, "track": "ui", "sfx": "none"}
           for i, t in enumerate(["A", "B", "A"])]
    plan = {"project": "_unit", "base": str(tmp_path), "timelines": [{"name": "T", "clips": [], "overlays": ovs}]}

    def fake_render(template, out, variables):
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_bytes(b"mov")
        return {"file": chr(92) * 2 + "?" + chr(92) + str(Path(out).resolve())}
    res = bp.render_assets(plan, plan["timelines"], render_fn=fake_render)
    assert res["rendered"] == 2 and res["copied"] == 1 and res["jobs"] == 3
    assert all(not o["file"].startswith(("//?/", chr(92))) and "\\" not in o["file"] for o in ovs)


# ---------- temporary English track and caption drafts ----------

def _temp_en_files(tmp_path, lines, english):
    vo = tmp_path / "vo.json"
    vo.write_text(json.dumps({"words": [], "lines": [{"text": f"l{i}", "start": a, "end": b}
                                                      for i, (a, b) in enumerate(lines)]}), encoding="utf-8")
    en = tmp_path / "script_en.txt"
    en.write_text("\n".join(english) + "\n", encoding="utf-8")
    return {"english": en.as_posix(), "timings": vo.as_posix()}


def test_build_adds_temp_en_on_its_own_track(tmp_path, monkeypatch):
    calls, post = _post_recorder()
    monkeypatch.setattr(bp.cp, "wait_for_draft", lambda p, t=30: Path(p))
    # Timeline 01: VO file 1.5 s .. 6.5 s (vo_in + 150 frames) plays at timeline 0 .. 5 s
    te = _temp_en_files(tmp_path, [(1.5, 2.5), (2.5, 4.0), (4.0, 6.5)], ["One.", "Two.", "Three."])
    plan = {**PLAN, "temp_en": te}
    res = bp.build_timeline(plan, plan["timelines"][0], post=post, render=False)
    rows = [b for e, b in calls if e == "add_text" and b["track_name"] == "TEMP_EN_delete_me"]
    assert [r["text"] for r in rows] == ["One.", "Two.", "Three."]
    assert [(r["start"], r["end"]) for r in rows] == [(0.0, 1.0), (1.0, 2.5), (2.5, 5.0)]
    assert all(r["transform_y"] == 0.85 and r["background_alpha"] == 0.6 and r["background_color"] == "#000000"
               and r["font_size"] == 7 and r["fixed_width"] == 0.9 and r["font_color"] == "#FFFFFF" for r in rows)
    assert res["counts"]["temp_en"] == 3


def test_temp_en_rows_outside_the_vo_span_are_dropped_and_partial_ones_clipped(tmp_path, monkeypatch):
    calls, post = _post_recorder()
    monkeypatch.setattr(bp.cp, "wait_for_draft", lambda p, t=30: Path(p))
    te = _temp_en_files(tmp_path, [(0.2, 1.0), (1.0, 2.0), (6.0, 7.0), (7.5, 8.0)], ["a", "b", "c", "d"])
    tl = {**PLAN["timelines"][0], "temp_en": te}       # a timeline's own temp_en
    bp.build_timeline(PLAN, tl, post=post, render=False)
    rows = [(b["text"], b["start"], b["end"]) for e, b in calls if e == "add_text"]
    assert rows == [("b", 0.0, 0.5), ("c", 4.5, 5.0)]


def test_no_temp_en_for_plain_plan(monkeypatch):
    calls, post = _post_recorder()
    monkeypatch.setattr(bp.cp, "wait_for_draft", lambda p, t=30: Path(p))
    res = bp.build_timeline(PLAN, PLAN["timelines"][0], post=post, render=False)
    assert not [b for e, b in calls if e == "add_text"] and res["counts"]["temp_en"] == 0


def test_temp_en_removed_flag_skips_it(tmp_path, monkeypatch):
    calls, post = _post_recorder()
    monkeypatch.setattr(bp.cp, "wait_for_draft", lambda p, t=30: Path(p))
    plan = {**PLAN, "temp_en": _temp_en_files(tmp_path, [(1.5, 2.5)], ["One."]), "temp_en_removed": True}
    bp.build_timeline(plan, plan["timelines"][0], post=post, render=False)
    assert not [b for e, b in calls if e == "add_text"]


def test_build_raises_temp_en_after_compose(tmp_path, monkeypatch):
    _stub_project(monkeypatch, [])
    raised = []
    monkeypatch.setattr(bp.cp, "raise_text_track", lambda project, name, track: raised.append((name, track)) or {})
    _, post = _post_recorder()
    plan, plan_path = _agent_plan(tmp_path)
    for n, o in enumerate(plan["timelines"][0]["overlays"], 1):
        o["file"] = (tmp_path / f"ov{n}.mov").as_posix()
    plan["temp_en"] = _temp_en_files(tmp_path, [(1.5, 2.5)], ["One."])
    res = bp.build(plan, job="_unit_build", post=post, render=False)
    assert raised == [("Timeline 01", "TEMP_EN_delete_me")] and res["counts"]["temp_en"] == 1


def test_captions_draft_one_text_per_chunk(monkeypatch):
    calls, post = _post_recorder()
    monkeypatch.setattr(bp.cp, "wait_for_draft", lambda p, t=30: Path(p))
    chunks = [{"text": "hola a todos", "start": 0.1, "end": 1.0}, {"text": "esto es", "start": 1.0, "end": 1.6},
              {"text": "una prueba.", "start": 1.6, "end": 2.4}]
    bp.captions_draft(chunks, {**PLAN, "captions_style": {"font_size": 11}}, post=post)
    texts = [b for e, b in calls if e == "add_text"]
    assert [b["track_name"] for b in texts] == ["captions"] * 3
    assert [(b["text"], b["start"], b["end"]) for b in texts] == [("hola a todos", 0.1, 1.0), ("esto es", 1.0, 1.6),
                                                                  ("una prueba.", 1.6, 2.4)]
    t = texts[0]
    assert t["font_size"] == 11 and t["bold"] is True and t["border_width"] == 0.08 and t["border_color"] == "#000000"
    assert t["transform_y"] == -0.62 and t["intro_animation"] == "Pop_Up" and t["intro_duration"] == 0.13
    assert t["shadow_enabled"] is True and "background_color" not in t and t["font"] == "Poppins_Bold"
    assert [e for e, _ in calls][-1] == "save_draft"


def test_captions_command_chunks_through_the_timeline_and_merges(tmp_path, monkeypatch, capsys):
    vo = tmp_path / "vo.json"
    vo.write_text(json.dumps({"words": [{"word": w, "start": 1.5 + i * 0.4, "end": 1.5 + i * 0.4 + 0.35}
                                        for i, w in enumerate("hello there how are you".split())],
                              "lines": []}), encoding="utf-8")
    script = tmp_path / "s.txt"
    script.write_text("Hello there, how are you?\n", encoding="utf-8")
    plan_p = tmp_path / "plan.json"
    plan_p.write_text(json.dumps(PLAN), encoding="utf-8")
    dump = {"timeline": "Timeline 01", "segments": [
        {"track": "vo", "track_type": "audio", "at": 0.0, "duration": 5.0, "src_in": 1.5, "speed": 1.0},
        {"track": "TEMP_EN_delete_me", "track_type": "text", "at": 0.0, "duration": 1.0}]}
    seen = {}
    monkeypatch.setattr(bp.cp, "segments", lambda project, name, dirs=(): dump)
    monkeypatch.setattr(bp, "captions_draft", lambda chunks, plan, post=None: seen.update(chunks=chunks) or "/draft")
    monkeypatch.setattr(bp.cp, "add_tracks", lambda project, name, draft, track_type="audio", on_top=False:
                        seen.update(add=(name, Path(draft).as_posix(), track_type)) or {"tracks_added": 1})
    monkeypatch.setattr(bp.cp, "raise_text_track", lambda project, name, track: seen.update(raised=track) or {})
    bp.main(["captions", str(plan_p), "Timeline 01", "--project", str(tmp_path / "proj"), "--script", str(script),
             "--timings", str(vo)])
    out = json.loads(capsys.readouterr().out)
    assert out["draft"] == "/draft" and out["chunks"] == len(seen["chunks"]) >= 1 and out["track"] == "captions"
    assert out["dropped_words"] == []
    assert seen["chunks"][0]["start"] == 0.0 and seen["add"] == ("Timeline 01", "/draft", "text")
    assert seen["raised"] == "TEMP_EN_delete_me"   # the review track stays above the captions


def test_temp_en_and_captions_end_to_end(tmp_path, monkeypatch, capsys):
    if not _api_up():
        pytest.skip("VectCutAPI not running on :9001")
    monkeypatch.setattr(cp, "_capcut_running", lambda: False)
    base = TMP / "_test_fixture" / "build_project"
    a = _synthetic(base / "clip_a.mp4", "testsrc2")
    vo = _synthetic(base / "vo.mp4", "testsrc")
    words = "hola a todos esto es una prueba de subtitulos".split()
    timings = tmp_path / "vo.json"
    timings.write_text(json.dumps({"words": [{"word": w, "start": 0.2 + i * 0.4, "end": 0.55 + i * 0.4}
                                             for i, w in enumerate(words)],
                                   "lines": [{"start": 0.2, "end": 1.75}, {"start": 1.8, "end": 3.75}]}),
                       encoding="utf-8")
    script = tmp_path / "script.txt"
    script.write_text("Hola a todos.\nEsto es una prueba de subtitulos.\n", encoding="utf-8")
    en = tmp_path / "script_en.txt"
    en.write_text("Hi everyone.\nThis is a caption test.\n", encoding="utf-8")
    name = f"_test_captions_{time.strftime('%Y%m%d-%H%M%S')}"
    plan = {"project": name, "fps": 30, "width": 1080, "height": 1920, "base": tmp_path.as_posix(),
            "temp_en": {"english": en.as_posix(), "timings": timings.as_posix()},
            "timelines": [{"name": "Timeline 01", "vo": vo, "vo_in": 0.0, "vo_out": 4.0, "vo_volume": 1.0,
                           "music": None, "music_volume": 0.1, "manual": [], "texts": [], "overlays": [],
                           "clips": [{**CLIP, "file": a, "src_in": 0.0, "src_out": 4.0, "at": 0.0}]}]}
    plan_p = tmp_path / "plan.json"
    plan_p.write_text(json.dumps(plan), encoding="utf-8")
    project = Path(PATHS["capcut_drafts"]) / name
    try:
        bp.build(plan, job=name, render=False)
        bp.main(["captions", str(plan_p), "Timeline 01", "--project", str(project), "--script", str(script),
                 "--timings", str(timings)])
        out = json.loads(capsys.readouterr().out)
        assert out["track"] == "captions" and out["chunks"] >= 2 and out["dropped_words"] == []
        segs = cp.segments(project, "Timeline 01")["segments"]
        assert {s["track"] for s in segs if s["track_type"] == "text"} == {"TEMP_EN_delete_me", "captions"}
        caps = [s["text"] for s in segs if s["track"] == "captions"]
        assert " ".join(caps).split() == "Hola a todos. Esto es una prueba de subtitulos.".split()
        assert [s["text"] for s in segs if s["track"] == "TEMP_EN_delete_me"] == ["Hi everyone.", "This is a caption test."]
        tl = cp._find(project, "Timeline 01")
        content = cp._read(cp._content_file(project / "Timelines" / tl["id"]))
        idx = {t["name"]: [s["render_index"] for s in t["segments"]] for t in content["tracks"] if t["type"] == "text"}
        assert min(idx["TEMP_EN_delete_me"]) > max(idx["captions"])   # CapCut layers text by segment render_index
    finally:
        if project.exists() and project.name.startswith("_test_"):
            shutil.rmtree(project, ignore_errors=True)


def test_temp_en_and_captions_default_to_a_latin_font_the_plan_can_override():
    te = bp.text_body("d", {"text": "Hi", "at": 0, "duration": 1, "style": "temp_en"}, PLAN, bp.TEMP_EN_TRACK)
    assert te["font"] == "Poppins_Regular" and te["track_name"] == "TEMP_EN_delete_me"
    c = bp.text_body("d", {"text": "Hola", "at": 0, "duration": 1, "style": "caption"},
                     {**PLAN, "captions_style": {"font": "Nunito"}})
    assert c["font"] == "Nunito"
    assert "font" not in bp.text_body("d", {"text": "X", "at": 0, "duration": 1, "style": "badge"}, PLAN)


def test_caption_frames_never_overlap_and_drop_empty_chunks():
    chunks = [{"text": "a", "start": 0.0, "end": 0.0}, {"text": "b", "start": 0.01, "end": 0.5},
              {"text": "c", "start": 0.5, "end": 0.5}, {"text": "d", "start": 0.6, "end": 0.6}]
    got = [(c["text"], a, e) for c, a, e in bp.caption_frames(chunks)]
    # a rounds onto b's start frame (dropped); c gets one frame up to d; d gets one frame
    assert got == [("b", 0, 15), ("c", 15, 16), ("d", 18, 19)]


def test_timeline_command_asks_for_the_temp_en_raise(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(bp, "build_timeline", lambda plan, tl, post=None: {"draft": "/d", "counts": {"temp_en": 2}})
    monkeypatch.setattr(bp, "save_built", lambda plan, tl, name=None, job=None: None)
    p = tmp_path / "plan.json"
    p.write_text(json.dumps(PLAN), encoding="utf-8")
    bp.main(["timeline", str(p), "Timeline 01"])
    assert json.loads(capsys.readouterr().out) == {"draft": "/d", "raise_text": "TEMP_EN_delete_me"}
    monkeypatch.setattr(bp, "build_timeline", lambda plan, tl, post=None: {"draft": "/d", "counts": {"temp_en": 0}})
    bp.main(["timeline", str(p), "Timeline 01"])
    assert json.loads(capsys.readouterr().out) == {"draft": "/d"}


def test_raise_temp_en_command(monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(bp.cp, "raise_text_track", lambda project, name, track: seen.append((Path(project).name, name, track))
                        or {"track": track})
    bp.main(["raise-temp-en", "/drafts/Proj", "Timeline 02"])
    assert seen == [("Proj", "Timeline 02", "TEMP_EN_delete_me")]
    assert json.loads(capsys.readouterr().out) == {"track": "TEMP_EN_delete_me"}


def test_captions_refused_when_the_timeline_already_has_captions(tmp_path, monkeypatch):
    vo = tmp_path / "vo.json"
    vo.write_text(json.dumps({"words": [{"word": "hi", "start": 0.0, "end": 0.3}]}), encoding="utf-8")
    script = tmp_path / "s.txt"
    script.write_text("Hi\n", encoding="utf-8")
    plan_p = tmp_path / "plan.json"
    plan_p.write_text(json.dumps(PLAN), encoding="utf-8")
    monkeypatch.setattr(bp.cp, "segments", lambda project, name, dirs=(): {"segments": [
        {"track": "captions", "track_type": "text", "at": 0.0, "duration": 1.0}]})
    made = []
    monkeypatch.setattr(bp, "captions_draft", lambda chunks, plan, post=None: made.append(1) or "/d")
    with pytest.raises(SystemExit, match="already has a 'captions' text track"):
        bp.main(["captions", str(plan_p), "Timeline 01", "--project", str(tmp_path), "--script", str(script),
                 "--timings", str(vo)])
    assert made == []


def test_captions_timings_prefer_the_timelines_own_temp_en(tmp_path, monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(bp, "add_captions", lambda plan, name, project, script, timings, mw, vt:
                        seen.update(timings=timings) or {})
    plan = {**PLAN, "captions": {"script": "/s.txt", "timings": "/plan_vo.json"},
            "temp_en": {"english": "/en.txt", "timings": "/te_vo.json"},
            "timelines": [{**PLAN["timelines"][0], "temp_en": {"english": "/h.txt", "timings": "/hook_vo.json"}}]}
    p = tmp_path / "plan.json"
    p.write_text(json.dumps(plan), encoding="utf-8")
    bp.main(["captions", str(p), "Timeline 01", "--project", "/x"])
    assert seen["timings"] == "/hook_vo.json"
    plan["timelines"][0].pop("temp_en")
    p.write_text(json.dumps(plan), encoding="utf-8")
    bp.main(["captions", str(p), "Timeline 01", "--project", "/x"])
    assert seen["timings"] == "/plan_vo.json"
