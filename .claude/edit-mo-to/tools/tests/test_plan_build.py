import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import plan_build as pb  # noqa: E402


def _ov(template, f, t, sfx="default", **vars):
    return {"template": template, "from": f, "to": t, "track": "ui", "vars": vars, "sfx": sfx}


def test_default_cue_resolves_file_time_and_trim():
    cues = pb.sfx_cues([_ov("glass-card", 30, 60)])
    assert len(cues) == 1
    c = cues[0]
    assert c["file"].endswith("pop.mp3") and Path(c["file"]).exists()
    assert c["at_us"] == pb.US(30) + 30_000 and c["len_us"] == 600_000 and 0 < c["volume"] <= 1


def test_offsets_can_follow_template_vars_and_conditions():
    verdict = pb.sfx_cues([_ov("glass-compare", 0, 60, mode="verdict", t_verdict=0.42)])
    mirror = pb.sfx_cues([_ov("glass-compare", 0, 60, mode="mirror", t_verdict=0.42)])
    assert [Path(c["file"]).stem for c in verdict] == ["pop", "ping"]
    assert verdict[1]["at_us"] == 420_000
    assert [Path(c["file"]).stem for c in mirror] == ["pop"]


def test_list_offsets_give_one_cue_per_time_and_fall_back_to_defaults():
    cues = pb.sfx_cues([_ov("cursor-ui", 0, 120, t_clicks="0.5,1.5")])
    assert [c["at_us"] for c in cues if Path(c["file"]).stem == "click"] == [500_000, 1_500_000]
    dflt = pb.sfx_cues([_ov("cursor-ui", 0, 120)])
    assert [c["at_us"] for c in dflt if Path(c["file"]).stem == "click"] == [900_000, 1_600_000, 2_400_000]


def test_none_and_custom_cues():
    assert pb.sfx_cues([_ov("badge", 0, 30, sfx="none")]) == []
    cues = pb.sfx_cues([_ov("badge", 0, 30, sfx=[{"name": "sparkle", "offset": 0.1, "len": 1.0, "volume": 0.3}])])
    assert Path(cues[0]["file"]).stem == "sparkle" and cues[0]["at_us"] == 100_000


def test_cues_never_overlap_on_a_track_and_never_pass_the_end():
    ovs = [_ov("color-flash", 0, 15), _ov("kinetic-title", 3, 39), _ov("glass-card", 5, 39), _ov("badge", 6, 30)]
    cues = pb.sfx_cues(ovs, end_us=pb.US(20))
    by_track = {}
    for c in cues:
        by_track.setdefault(c["track"], []).append(c)
    for track, cs in by_track.items():
        cs.sort(key=lambda c: c["at_us"])
        for a, b in zip(cs, cs[1:]):
            assert a["at_us"] + a["len_us"] <= b["at_us"], track
    assert all(c["at_us"] + c["len_us"] <= pb.US(20) for c in cues)
    assert len(cues) == 3  # the title whoosh 0.1s after the flash whoosh is merged away


def test_stacked_whooshes_merge_into_one():
    cues = pb.sfx_cues([_ov("color-flash", 0, 15), _ov("kinetic-title", 3, 39), _ov("kinetic-title", 39, 60)])
    names = [(Path(c["file"]).stem, round(c["at_us"] / 1e6, 2)) for c in cues]
    assert names == [("whoosh", 0.0), ("whoosh-short", 1.3)]


# ---- beat_snap: overlay starts land on the music's beats ----

def test_beat_snap_moves_starts_within_tolerance_and_keeps_length():
    ovs = [_ov("badge", 29, 59), _ov("cta", 100, 130), _ov("stat", 46, 70)]
    beats = [1.0, 1.5, 2.0]                       # frames 30, 45, 60
    moves = pb.beat_snap(ovs, beats, tol=2)
    assert [(o["from"], o["to"]) for o in ovs] == [(30, 60), (100, 130), (45, 69)]
    assert [(m["index"], m["from"], m["to"]) for m in moves] == [(0, 29, 30), (2, 46, 45)]


def test_beat_snap_honours_music_offset_opt_out_and_start_of_timeline():
    ovs = [_ov("badge", 62, 90), _ov("cta", 62, 90), _ov("stat", 1, 20)]
    ovs[1]["snap"] = False
    moves = pb.beat_snap(ovs, [1.0, 0.0], tol=3, music_at=30)   # music starts at frame 30: beats at 60, 30
    assert ovs[0]["from"] == 60 and ovs[0]["to"] == 88
    assert ovs[1]["from"] == 62                                   # opted out
    assert ovs[2]["from"] == 1                                    # no beat within 3 frames
    assert len(moves) == 1


def test_beat_snap_cli_writes_snapped_plan(tmp_path):
    import json
    plan = {"overlays": [_ov("badge", 31, 61)]}
    (tmp_path / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    (tmp_path / "beats.json").write_text(json.dumps({"tempo": 120, "beats": [1.0]}), encoding="utf-8")
    pb.main([str(tmp_path / "plan.json"), "--snap-beats", str(tmp_path / "beats.json"), "--tol", "2",
             "--out", str(tmp_path / "snapped.json")])
    out = json.loads((tmp_path / "snapped.json").read_text(encoding="utf-8"))
    assert out["overlays"][0]["from"] == 30 and out["overlays"][0]["to"] == 60


def test_beat_snap_only_moves_listed_tracks():
    ovs = [_ov("badge", 29, 59), {**_ov("color-flash", 29, 40), "track": "flash"}]
    pb.beat_snap(ovs, [1.0], tol=2, tracks=["flash"])
    assert ovs[0]["from"] == 29 and ovs[1]["from"] == 30
