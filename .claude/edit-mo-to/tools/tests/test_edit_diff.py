import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import edit_diff as ed  # noqa: E402
from test_capcut_patch import project  # noqa: E402,F401  (synthetic CapCut project fixture)


def seg(track, src, at, dur, src_in=0.0, volume=1.0, scale=1.0, x=0.0, y=0.0, ttype="video", text=None):
    return {"track": track, "track_type": ttype, "material_type": "texts" if text else "videos", "source": src,
            "path": src, "at": at, "duration": dur, "src_in": src_in, "volume": volume, "speed": 1.0,
            "scale": {"x": scale, "y": scale}, "transform": {"x": x, "y": y}, "text": text}


def tl(segs, name="Timeline 01"):
    return {"timeline": name, "duration": max(s["at"] + s["duration"] for s in segs), "segments": segs}


def test_kinds():
    assert ed.kind(seg("video_main", "D:/a.mp4", 0, 1)) == "a-roll"
    assert ed.kind(seg("video_broll", "D:/b.mp4", 0, 1)) == "b-roll"
    assert ed.kind(seg("overlay_ui", "D:/x/motion/T1_01_badge.mov", 0, 1)) == "overlay"
    assert ed.kind(seg("sfx_a", "D:/sfx/pop.mp3", 0, 1, ttype="audio")) == "sfx"
    assert ed.kind(seg("music", "D:/m.mp3", 0, 1, ttype="audio")) == "music"
    assert ed.kind(seg("text", None, 0, 1, ttype="text", text="hi")) == "text"


def test_no_edits_no_changes():
    b = tl([seg("video_main", "a.mp4", 0, 3), seg("video_broll", "b.mp4", 1, 1)])
    d = ed.diff(b, b)
    assert d["changed"] == [] and d["removed"] == [] and d["added"] == [] and d["patterns"] == []


def test_detects_trims_moves_volume_and_patterns():
    built = tl([seg("video_main", "a.mp4", 0, 9),
                seg("video_broll", "b1.mp4", 1.0, 2.0), seg("video_broll", "b2.mp4", 4.0, 2.0),
                seg("video_broll", "b3.mp4", 7.0, 2.0),
                seg("overlay_ui", "m/motion/c1.mov", 1.5, 2.0), seg("overlay_ui", "m/motion/c2.mov", 4.6, 2.0),
                seg("music", "song.mp3", 0, 9, volume=0.1, ttype="audio")])
    final = tl([seg("video_main", "a.mp4", 0, 9),
                seg("video_broll", "b1.mp4", 1.0, 1.4), seg("video_broll", "b2.mp4", 4.0, 1.5),
                seg("video_broll", "b3.mp4", 7.0, 1.2),
                seg("overlay_ui", "m/motion/c1.mov", 1.0, 2.0), seg("overlay_ui", "m/motion/c2.mov", 4.0, 2.0),
                seg("music", "song.mp3", 0, 9, volume=0.05, ttype="audio"),
                seg("text", None, 0.2, 1.0, ttype="text", text="caption")])
    d = ed.diff(built, final)
    ids = {p["id"] for p in d["patterns"]}
    assert "b-roll:shorter" in ids
    assert "overlay:to-cut" in ids and "overlay:earlier" in ids
    assert "music:quieter" in ids
    assert d["caption_segments_added"] == 1 and d["added"] == []  # captions are counted, not learned from
    music = next(c for c in d["changed"] if c["kind"] == "music")
    assert music["volume_db"] == -6.0


def test_removed_and_added():
    built = tl([seg("video_main", "a.mp4", 0, 6), seg("overlay_ui", "m/motion/zoom.mov", 2, 1)])
    final = tl([seg("video_main", "a.mp4", 0, 6), seg("video_broll", "mine.mp4", 3, 2)])
    d = ed.diff(built, final)
    assert d["removed"][0]["kind"] == "overlay" and d["added"][0]["file"] == "mine.mp4"
    ids = {p["id"] for p in d["patterns"]}
    assert {"overlay:removed", "b-roll:added"} <= ids


def test_recurring_across_videos(tmp_path):
    log = tmp_path / "p.jsonl"
    rows = [{"video": "A", "patterns": [{"id": "b-roll:shorter", "text": "x"}]},
            {"video": "B", "patterns": [{"id": "b-roll:shorter", "text": "y"}, {"id": "music:quieter", "text": "z"}]}]
    log.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    rec = ed.recurring(log)
    assert [r["id"] for r in rec] == ["b-roll:shorter"] and rec[0]["videos"] == 2


def test_diff_last_with_no_hand_edits_is_empty(project, capsys):
    from test_capcut_patch import cp
    # our own patch is snapshotted, so it is not read as a hand edit
    cp.patch_timeline(project, "Timeline 01", [{"op": "set", "id": "a2", "scale": 1.6, "speed": 0.93}])
    ed.main(["diff", "--last", str(project), "Timeline 01"])
    res = json.loads(capsys.readouterr().out)
    assert res["changed"] == [] and res["patterns"] == []


def test_diff_last_sees_only_hand_edits(project, capsys):
    from test_capcut_patch import cp, _load, S
    cp.patch_timeline(project, "Timeline 01", [{"op": "set", "id": "a2", "scale": 1.6}])
    # the editor trims a clip in CapCut afterwards (written straight to the content file, no snapshot)
    folder = project / "Timelines" / "TL1"
    c = _load(project)
    seg = next(s for t in c["tracks"] for s in t["segments"] if s["id"] == "b1")
    seg["target_timerange"]["duration"] = S
    (folder / "draft_content.json").write_text(json.dumps(c), encoding="utf-8")
    ed.main(["diff", "--last", str(project), "Timeline 01"])
    res = json.loads(capsys.readouterr().out)
    assert [(c["kind"], c["length"]) for c in res["changed"]] == [("b-roll", -1.0)]


def test_diff_last_missing_snapshot_is_a_json_error(project, capsys):
    import pytest
    with pytest.raises(SystemExit) as e:
        ed.main(["diff", "--last", str(project), "Timeline 01"])
    assert e.value.code == 1
    assert "no last-write snapshot" in json.loads(capsys.readouterr().out)["error"]


def test_diff_last_hash_named_clip_is_not_removed_plus_added(project, tmp_path, capsys):
    from test_capcut_patch import cp, _load
    clip = tmp_path / "client" / "V01.mp4"
    clip.parent.mkdir()
    clip.write_bytes(b"x")
    folder = project / "Timelines" / "TL1"
    c = _load(project)
    m = next(m for m in c["materials"]["videos"] if m["id"] == "mb1")
    m["path"] = f"D:/proj/assets/video_{cp._vectcut_hash(clip.as_posix())}.mp4"
    (folder / "draft_content.json").write_text(json.dumps(c), encoding="utf-8")
    os.utime(folder / "draft_content.json", (1_700_000_000, 1_700_000_000))  # not "just edited by CapCut"
    cp.patch_timeline(project, "Timeline 01", [{"op": "set", "id": "a1", "volume": 0.8}])
    ed.main(["diff", "--last", str(project), "Timeline 01", str(clip.parent)])
    res = json.loads(capsys.readouterr().out)
    assert res["removed"] == [] and res["added"] == [] and res["changed"] == []


def test_temp_en_deletion_is_not_a_pattern():
    keep = seg("video_main", "a.mp4", 0, 9)
    en = [seg("TEMP_EN_delete_me", None, i, 1.0, ttype="text", text=f"line {i}") for i in range(3)]
    d = ed.diff(tl([keep, *en]), tl([keep]))
    assert d["removed"] == [] and d["added"] == [] and d["patterns"] == []
    d = ed.diff(tl([keep]), tl([keep, *en]))
    assert d["caption_segments_added"] == 0 and d["added"] == []
