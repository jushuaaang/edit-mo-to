"""patch: edit a hand-edited timeline in place, op by op. Uses a small synthetic CapCut 9.6 project
(no VectCutAPI needed)."""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import capcut_project as cp  # noqa: E402

S = 1_000_000


def _video_mat(mid, path, dur=4 * S):
    return {"id": mid, "material_id": mid, "local_material_id": "", "unique_id": "u" + mid, "type": "video",
            "duration": dur, "path": path, "material_name": Path(path).name, "width": 1080, "height": 1920,
            "crop": dict(cp.FULL_FRAME_CROP)}


def _companions(prefix, speed=1.0):
    return {"speeds": {"id": prefix + "-sp", "type": "speed", "mode": 0, "speed": speed, "curve_speed": None},
            "canvases": {"id": prefix + "-cv", "type": "canvas_color", "color": "", "blur": 0.0}}


def _seg(sid, mid, start, dur, src=0, speed=1.0, scale=1.4222, y=0.0, volume=0.0, kf=None):
    return {"id": sid, "material_id": mid, "extra_material_refs": [sid + "-sp", sid + "-cv"],
            "target_timerange": {"start": start, "duration": dur},
            "source_timerange": {"start": src, "duration": int(dur * speed)}, "speed": speed, "volume": volume,
            "last_nonzero_volume": 1.0, "keyframe_refs": [], "common_keyframes": kf or [],
            "clip": {"scale": {"x": scale, "y": scale}, "rotation": 0.0, "transform": {"x": 0.0, "y": y},
                     "flip": {"vertical": False, "horizontal": False}, "alpha": 1.0}}


def _content():
    kf = [{"id": "kf1", "property_type": "KFTypeScaleX",
           "keyframe_list": [{"id": "k1", "time_offset": 0, "values": [1.0]},
                             {"id": "k2", "time_offset": 2 * S, "values": [1.06]}]}]
    segs_main = [_seg("a1", "ma1", 0, 3 * S, src=0, y=-0.2, volume=1.0),
                 _seg("a2", "ma2", 3 * S, 4 * S, src=3 * S, y=-0.2, volume=1.0)]
    segs_broll = [_seg("b1", "mb1", 1 * S, 2 * S, kf=kf)]
    audio_seg = {"id": "s1", "material_id": "mau", "extra_material_refs": ["s1-sp"],
                 "target_timerange": {"start": 0, "duration": S // 2},
                 "source_timerange": {"start": 0, "duration": S // 2}, "speed": 1.0, "volume": 0.4,
                 "keyframe_refs": [], "common_keyframes": []}
    mats = {"videos": [_video_mat("ma1", "D:/x/SCRIPT.mp4", 300 * S), _video_mat("ma2", "D:/x/SCRIPT.mp4", 300 * S),
                       _video_mat("mb1", "D:/x/V01.mp4")],
            "audios": [{"id": "mau", "music_id": "mau", "local_material_id": "mau", "type": "extract_music",
                        "name": "whoosh.mp3", "duration": S // 2, "path": "D:/x/whoosh.mp3"}],
            "speeds": [], "canvases": []}
    for sid in ("a1", "a2", "b1", "s1"):
        c = _companions(sid)
        mats["speeds"].append(c["speeds"])
        if sid != "s1":
            mats["canvases"].append(c["canvases"])
    return {"id": "TL1", "duration": 7 * S, "canvas_config": {"ratio": "custom", "width": 1080, "height": 1350},
            "materials": mats,
            "tracks": [{"id": "t1", "type": "video", "name": "video_main", "segments": segs_main},
                       {"id": "t2", "type": "video", "name": "video_broll", "segments": segs_broll},
                       {"id": "t3", "type": "audio", "name": "sfx_a", "segments": [audio_seg]}]}


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A CapCut 9.6-style project: the user's edits live in draft_content.json; draft_info.json is stale."""
    monkeypatch.setattr(cp, "_capcut_running", lambda: False)
    monkeypatch.setattr(cp, "_probe_media", lambda p: {"duration_us": 4 * S, "width": 1080, "height": 1920,
                                                       "kind": "audio" if p.endswith(".mp3") else "video"})
    proj = tmp_path / "Proj"
    folder = proj / "Timelines" / "TL1"
    folder.mkdir(parents=True)
    c = _content()
    stale = dict(c, duration=1)
    for f in (folder, proj):
        (f / "draft_info.json").write_text(json.dumps(stale), encoding="utf-8")
        (f / "draft_content.json").write_text(cp._dump_exact(c), encoding="utf-8")
        os.utime(f / "draft_info.json", (1_000_000_000, 1_000_000_000))
    (proj / "Timelines" / "project.json").write_text(json.dumps({
        "id": "P", "main_timeline_id": "TL1", "timelines": [{"id": "TL1", "name": "Timeline 01", "is_marked_delete": False}]}),
        encoding="utf-8")
    old = 1_700_000_000
    for f in proj.rglob("*.json"):
        os.utime(f, (old, old)) if f.name != "draft_info.json" else None
    return proj


def _load(proj):
    return json.loads((proj / "Timelines" / "TL1" / "draft_content.json").read_text(encoding="utf-8"))


def _seg_by(c, sid):
    return next(s for t in c["tracks"] for s in t["segments"] if s["id"] == sid)


def test_set_retimes_and_scales_and_keeps_others_byte_for_byte(project):
    before = _load(project)
    cp.patch_timeline(project, "Timeline 01", [{"op": "set", "id": "a2", "scale": 1.6355, "speed": 0.9302}])
    after = _load(project)
    s = _seg_by(after, "a2")
    assert s["clip"]["scale"] == {"x": 1.6355, "y": 1.6355} and s["speed"] == 0.9302
    assert next(m for m in after["materials"]["speeds"] if m["id"] == "a2-sp")["speed"] == 0.9302
    for sid in ("a1", "b1", "s1"):
        assert _seg_by(after, sid) == _seg_by(before, sid)


def test_patch_reads_and_writes_draft_content_not_stale_info(project):
    cp.patch_timeline(project, "Timeline 01", [{"op": "set", "id": "a1", "volume": 0.8}])
    folder = project / "Timelines" / "TL1"
    assert _seg_by(_load(project), "a2")["target_timerange"]["start"] == 3 * S  # base was draft_content
    assert (folder / "draft_content.json").stat().st_mtime > (folder / "draft_info.json").stat().st_mtime
    assert cp._content_file(folder).name == "draft_content.json"
    root = json.loads((project / "draft_content.json").read_text(encoding="utf-8"))
    assert _seg_by(root, "a1")["volume"] == 0.8  # main timeline: root copy updated


def test_ripple_shifts_every_track_and_keeps_keyframes(project):
    cp.patch_timeline(project, "Timeline 01", [
        {"op": "set", "id": "a1", "duration": 3 * S + 66_667},
        {"op": "ripple", "at": 3 * S, "delta": 66_667}])
    c = _load(project)
    assert _seg_by(c, "a2")["target_timerange"]["start"] == 3 * S + 66_667
    assert _seg_by(c, "b1")["target_timerange"]["start"] == 1 * S  # starts before the edge: unchanged
    assert _seg_by(c, "b1")["common_keyframes"][0]["keyframe_list"][1]["time_offset"] == 2 * S
    assert c["duration"] == 7 * S + 66_667


def test_split_makes_two_pieces_with_matching_source(project):
    out = cp.patch_timeline(project, "Timeline 01", [
        {"op": "split", "id": "a2", "at": 5 * S, "name": "right"},
        {"op": "set", "id": "@right", "scale": 1.6355}])
    c = _load(project)
    left, right = _seg_by(c, "a2"), _seg_by(c, out["results"][0]["new_id"])
    assert left["target_timerange"] == {"start": 3 * S, "duration": 2 * S}
    assert right["target_timerange"] == {"start": 5 * S, "duration": 2 * S}
    assert right["source_timerange"]["start"] == 3 * S + 2 * S
    assert right["clip"]["scale"]["x"] == 1.6355 and left["clip"]["scale"]["x"] == 1.4222
    assert right["material_id"] != left["material_id"]


def test_insert_points_a_new_material_at_the_file_and_creates_missing_track(project):
    out = cp.patch_timeline(project, "Timeline 01", [
        {"op": "insert", "track": "video_broll", "file": "D:/x/V61.mp4", "start": 4 * S, "duration": 2 * S},
        {"op": "insert", "track": "sfx_b", "file": "D:/x/pop.mp3", "start": 2 * S, "duration": S // 2, "volume": 0.5}])
    c = _load(project)
    new = _seg_by(c, out["results"][0]["id"])
    mat = next(m for m in c["materials"]["videos"] if m["id"] == new["material_id"])
    assert mat["path"] == "D:/x/V61.mp4" and mat["material_name"] == "V61.mp4"
    assert new["volume"] == 0.0 and new["source_timerange"] == {"start": 0, "duration": 2 * S}
    assert new["common_keyframes"] == [] and set(new["extra_material_refs"]).isdisjoint(_seg_by(c, "b1")["extra_material_refs"])
    sfx_b = next(t for t in c["tracks"] if t["name"] == "sfx_b")
    assert sfx_b["type"] == "audio" and len(sfx_b["segments"]) == 1


def test_set_with_file_repoints_only_that_segment(project):
    cp.patch_timeline(project, "Timeline 01", [{"op": "set", "id": "b1", "file": "D:/x/V21b.mp4"}])
    c = _load(project)
    mat = next(m for m in c["materials"]["videos"] if m["id"] == _seg_by(c, "b1")["material_id"])
    assert mat["path"] == "D:/x/V21b.mp4"
    assert next(m for m in c["materials"]["videos"] if m["id"] == "ma1")["path"] == "D:/x/SCRIPT.mp4"


def test_remove_drops_segment_and_its_orphan_materials(project):
    cp.patch_timeline(project, "Timeline 01", [{"op": "remove", "id": "b1"}])
    c = _load(project)
    assert all(s["id"] != "b1" for t in c["tracks"] for s in t["segments"])
    ids = {m["id"] for items in c["materials"].values() for m in items}
    assert not {"mb1", "b1-sp", "b1-cv"} & ids and "ma1" in ids


def test_overlap_is_refused_and_nothing_is_written(project):
    before = (project / "Timelines" / "TL1" / "draft_content.json").read_bytes()
    with pytest.raises(ValueError, match="overlap"):
        cp.patch_timeline(project, "Timeline 01", [{"op": "set", "id": "a1", "duration": 4 * S}])
    assert (project / "Timelines" / "TL1" / "draft_content.json").read_bytes() == before
    assert not (project / cp.BACKUP_DIR).exists()


def test_dry_run_writes_nothing(project):
    before = (project / "Timelines" / "TL1" / "draft_content.json").read_bytes()
    out = cp.patch_timeline(project, "Timeline 01", [{"op": "ripple", "at": 0, "delta": S}], dry_run=True)
    assert out["dry_run"] and out["duration"] == 8.0
    assert (project / "Timelines" / "TL1" / "draft_content.json").read_bytes() == before


def test_backup_is_made_before_writing(project):
    out = cp.patch_timeline(project, "Timeline 01", [{"op": "set", "id": "a1", "volume": 0.9}])
    bak = Path(out["backup"])
    assert json.loads((bak / "draft_content.json").read_text(encoding="utf-8"))["tracks"][0]["segments"][0]["volume"] == 1.0
    assert (bak / "root_draft_content.json").exists()


def test_refuses_while_capcut_running(project, monkeypatch):
    monkeypatch.setattr(cp, "_capcut_running", lambda: True)
    with pytest.raises(cp.ProjectBusy):
        cp.patch_timeline(project, "Timeline 01", [{"op": "set", "id": "a1", "volume": 0.9}])


def test_unknown_segment_is_a_clear_error(project):
    with pytest.raises(ValueError, match="no segment with id"):
        cp.patch_timeline(project, "Timeline 01", [{"op": "set", "id": "nope", "volume": 0.1}])
