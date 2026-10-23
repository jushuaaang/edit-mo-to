import copy
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import plan_tools as pt  # noqa: E402


def _p2(clips):
    return {"project": "T", "fps": 30, "width": 1080, "height": 1920, "base": "/v/", "brand": {}, "blocks": {},
            "timelines": [{"name": "T01", "seq": [{"clips": clips}]}]}


# frames: clip 1 at 0 len 30; clip 2 at 30 len 60 (1.0s, 2.0s); clip 3 at 90 len 30
CLIPS = [["a.mp4", 0, 0, 30], ["b.mp4", 15, 30, 60], ["c.mp4", 0, 90, 30]]
PLAN = pt.expand(_p2(CLIPS))


def _seg(sid, file, src_in, at, dur, track="video"):
    return {"id": sid, "track": track, "track_type": "video", "material_type": "videos", "source": file,
            "at": at, "duration": dur, "src_in": src_in, "speed": 1.0, "volume": 0.0,
            "transform": {"x": 0.0, "y": 0.0}, "scale": {"x": 1.0, "y": 1.0}}


DUMP = {"timeline": "T01", "duration": 4.0, "segments": [
    _seg("SEG1", "/v/a.mp4", 0.0, 0.0, 1.0),
    _seg("SEG2", "/v/b.mp4", 0.5, 1.0, 2.0),
    _seg("SEG3", "/v/c.mp4", 0.0, 3.0, 1.0),
    {**_seg("CAP", "", None, 0.0, 4.0, "caption"), "track_type": "text", "source": None}]}


def _revised(clips):
    return pt.expand(_p2(clips))


def test_moved_and_trimmed_clip_becomes_one_set_op():
    new = _revised([CLIPS[0], ["b.mp4", 15, 45, 45], CLIPS[2]])  # clip 2: at 1.0 -> 1.5, length 2.0 -> 1.5
    r = pt.ops(PLAN, new, "T01", DUMP)
    # patch units: integer microseconds; the source span follows the new length (speed 1)
    assert r["ops"] == [{"op": "set", "id": "SEG2", "start": 1500000, "duration": 1500000,
                         "src_duration": 1500000}]
    assert r["unmapped"] == []


def test_only_a_move_keeps_the_length():
    new = _revised([CLIPS[0], ["b.mp4", 15, 45, 60], CLIPS[2]])
    assert pt.ops(PLAN, new, "T01", DUMP)["ops"] == [{"op": "set", "id": "SEG2", "start": 1500000}]


def test_scale_position_speed_and_volume_changes():
    new = _revised([CLIPS[0], ["b.mp4", 15, 30, 30, {"scale": 1.2, "x": 0.1, "y": -0.2, "speed": 2.0, "mute": False}],
                    CLIPS[2]])
    [op] = pt.ops(PLAN, new, "T01", DUMP)["ops"]
    assert op == {"op": "set", "id": "SEG2", "duration": 1000000, "src_duration": 2000000, "speed": 2.0,
                  "scale": 1.2, "x": 0.1, "y": -0.2, "volume": 1.0}


def test_removed_and_added_rows():
    new = _revised([CLIPS[0], CLIPS[1], ["d.mp4", 6, 90, 45, {"track": "top"}]])  # clip 3 gone, a new one added
    r = pt.ops(PLAN, new, "T01", DUMP)
    assert r["ops"] == [
        {"op": "remove", "id": "SEG3"},
        {"op": "insert", "track": "video_top", "file": "/v/d.mp4", "start": 3000000, "duration": 1500000,
         "src_start": 200000, "speed": 1.0, "scale": 1.0, "x": 0.0, "y": 0.0, "volume": 0}]
    assert r["unmapped"] == []


def test_unmappable_row_is_reported_not_guessed():
    dump = copy.deepcopy(DUMP)
    dump["segments"][1]["source"] = "##_draftpath_placeholder_X_##/assets/video_0123456789abcdef.mp4"
    new = _revised([CLIPS[0], ["b.mp4", 15, 45, 60], CLIPS[2]])
    r = pt.ops(PLAN, new, "T01", dump)
    assert r["ops"] == []
    assert [u["row"] for u in r["unmapped"]] == ["/v/b.mp4 src_in 0.5 at 1.0"]
    assert "no segment" in r["unmapped"][0]["why"]


def test_identical_plans_give_no_ops():
    assert pt.ops(PLAN, PLAN, "T01", DUMP)["ops"] == []


def test_identical_plans_with_unmappable_source_stay_quiet():
    dump = copy.deepcopy(DUMP)
    dump["segments"][1]["source"] = "##_draftpath_placeholder_X_##/assets/video_0123456789abcdef.mp4"
    assert pt.ops(PLAN, PLAN, "T01", dump) == {"ops": [], "unmapped": []}


def test_paths_compare_after_slash_normalising_and_src_in_within_one_frame():
    dump = copy.deepcopy(DUMP)
    dump["segments"][1]["source"] = chr(92) + "v" + chr(92) + "b.mp4"
    dump["segments"][1]["src_in"] = 0.5 + 1 / 30  # one frame off still matches
    new = _revised([CLIPS[0], ["b.mp4", 15, 45, 60], CLIPS[2]])
    assert pt.ops(PLAN, new, "T01", dump)["ops"] == [{"op": "set", "id": "SEG2", "start": 1500000}]


def test_same_source_twice_pairs_each_row_to_its_own_segment():
    clips = [["a.mp4", 0, 0, 30], ["a.mp4", 0, 60, 30]]
    old = _revised(clips)
    dump = {"timeline": "T01", "segments": [_seg("S1", "/v/a.mp4", 0.0, 0.0, 1.0),
                                            _seg("S2", "/v/a.mp4", 0.0, 2.0, 1.0)]}
    new = _revised([clips[0], ["a.mp4", 0, 90, 30]])
    assert pt.ops(old, new, "T01", dump)["ops"] == [{"op": "set", "id": "S2", "start": 3000000}]


def test_unknown_timeline_is_an_error():
    try:
        pt.ops(PLAN, PLAN, "nope", DUMP)
    except ValueError as e:
        assert "nope" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_cli_writes_ops_json(tmp_path):
    (tmp_path / "old.json").write_text(json.dumps(PLAN), encoding="utf-8")
    (tmp_path / "new.json").write_text(json.dumps(_revised([CLIPS[0], ["b.mp4", 15, 45, 60], CLIPS[2]])),
                                       encoding="utf-8")
    (tmp_path / "dump.json").write_text(json.dumps(DUMP), encoding="utf-8")
    out = tmp_path / "ops.json"
    p = subprocess.run([sys.executable, str(Path(pt.__file__)), "ops", str(tmp_path / "old.json"),
                        str(tmp_path / "new.json"), "T01", "--segments", str(tmp_path / "dump.json"),
                        "--out", str(out)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert json.loads(out.read_text(encoding="utf-8"))["ops"] == [{"op": "set", "id": "SEG2", "start": 1500000}]
    assert json.loads(p.stdout)["ops"] == 1


def test_ops_dry_run_on_a_built_project(monkeypatch):
    """expand -> build a throwaway project -> revise one clip -> ops against the built timeline ->
    `capcut_project.py patch --dry-run` accepts the one set op."""
    import shutil
    import time
    import requests
    import build_project as bp
    import capcut_project as cp
    from machine import PATHS, TMP
    try:
        requests.post("http://localhost:9001/create_draft", json={"width": 1080, "height": 1920}, timeout=3)
    except requests.RequestException:
        import pytest
        pytest.skip("VectCutAPI not running on :9001")
    monkeypatch.setattr(cp, "_capcut_running", lambda: False)
    base = TMP / "_test_fixture" / "plan_ops"
    base.mkdir(parents=True, exist_ok=True)
    for n, pat in (("a.mp4", "testsrc2"), ("b.mp4", "smptebars")):
        if not (base / n).exists():
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i",
                            f"{pat}=size=1080x1920:rate=30:duration=6", "-pix_fmt", "yuv420p", str(base / n)], check=True)
    name = f"_test_ops_{time.strftime('%Y%m%d-%H%M%S')}"
    p2 = {**_p2([["a.mp4", 0, 0, 60], ["b.mp4", 30, 60, 60]]), "project": name, "base": base.as_posix()}
    p2["timelines"][0]["name"] = "Timeline 01"
    revised = copy.deepcopy(p2)
    revised["timelines"][0]["seq"][0]["clips"][1][2] = 75  # clip 2 starts half a second later
    old, new = pt.expand(p2), pt.expand(revised)
    project = Path(PATHS["capcut_drafts"]) / name
    try:
        bp.build(old, job=name)
        dump = cp.segments(project, "Timeline 01", [base])
        res = pt.ops(old, new, "Timeline 01", dump)
        assert res["unmapped"] == [] and [o["op"] for o in res["ops"]] == ["set"]
        assert res["ops"][0]["start"] == 2500000
        done = cp.patch_timeline(project, "Timeline 01", res, dry_run=True)
        assert done["ops_applied"] == 1
    finally:
        if project.name.startswith("_test_ops_"):
            shutil.rmtree(project, ignore_errors=True)
            shutil.rmtree(TMP / "reports" / name, ignore_errors=True)
