"""A clip's timeline length is the plan's len_f at every speed, through expand -> build body -> check ->
qa_check -> ops (slow clips used to come out a frame long or short: src_out rounding lost len_f)."""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_project as bp  # noqa: E402
import plan_tools as pt  # noqa: E402
import qa_check as qc  # noqa: E402
from plan_common import US, clip_len_f  # noqa: E402

SPEEDS = [round(0.5 + 0.05 * i, 2) for i in range(31)]      # 0.5 .. 2.0
LENGTHS = range(1, 121)
PROBE = lambda p: {"duration": 600.0, "width": 1080, "height": 1920, "fps": 30, "rotation": 0}  # noqa: E731
QUIET = lambda p, t, **k: True  # noqa: E731


def _plan(speed: float) -> dict:
    rows, at = [], 0
    for n in LENGTHS:   # back to back on the main track, one file each (no reuse)
        rows.append([f"c{n}.mp4", 7, at, n, {"speed": speed}])
        at += n
    return pt.expand({"project": "P", "fps": 30, "width": 1080, "height": 1920, "base": "/v/", "vo": None,
                      "music": None, "timelines": [{"name": "T", "seq": [{"clips": rows}]}]})


@pytest.mark.parametrize("speed", SPEEDS)
def test_length_is_len_f_through_every_tool(speed):
    plan = _plan(speed)
    tl = plan["timelines"][0]
    clips = tl["clips"]
    at = 0
    for n, c in zip(LENGTHS, clips):
        # expand
        assert clip_len_f(c) == n, (speed, n)
        # build
        assert bp.clip_frames(c) == (at, n), (speed, n)
        b = bp.clip_body("d", c, (1080, 1920))
        assert round(b["target_start"] * 1e6) == US(at)
        assert abs((b["end"] - b["start"]) * 1e6 / speed - (US(at + n) - US(at))) <= 1 + 1e-6, (speed, n)
        # check / qa_check share this
        assert round(pt._clip_len(c) * 30) == n
        # ops
        assert pt._facts(c)["duration"] == US(at + n) - US(at)
        at += n
    assert bp.end_frame(tl) == at
    # check: back-to-back clips leave no gap and no overlap
    assert pt.check(plan, probe=PROBE, silent=QUIET) == []
    # qa_check: the built segments are present at their planned length, nothing extra
    segs = []
    for c in clips:
        b = bp.clip_body("d", c, (1080, 1920))
        segs.append({"track": "video", "track_type": "video", "material_type": "videos", "source": c["file"],
                     "path": c["file"], "remote_url": None, "size": "1080x1920", "text": None,
                     "at": b["target_start"], "duration": (b["end"] - b["start"]) / speed, "src_in": b["start"],
                     "speed": speed, "volume": 0.0, "transform": {"x": 0.0, "y": 0.0}, "scale": {"x": 1.0, "y": 1.0},
                     "rotation": 0.0, "crop": None, "mask": []})
    dump = {"timeline": "T", "duration": at / 30, "segments": segs}
    r = qc.check_build(plan, Path("/p"), segments_fn=lambda p, n, s: copy.deepcopy(dump), probe=PROBE, silent=QUIET)
    assert [row for row in r["rows"] if row["check"] in ("present", "extras", "tracks_volumes")] == []
    # ops: moving every clip one frame keeps every length
    moved = copy.deepcopy(plan)
    for c in moved["timelines"][0]["clips"]:
        c["at"] = pt.sec(round(c["at"] * 30) + 1)
    seg_dump = {"segments": [{**s, "id": f"s{i}"} for i, s in enumerate(segs)]}
    res = pt.ops(plan, moved, "T", seg_dump)
    assert res["unmapped"] == [] and len(res["ops"]) == len(clips)
    by_id = {f"s{i}": n for i, n in enumerate(LENGTHS)}
    for o in res["ops"]:   # a one-µs duration change from the new start's rounding is fine; a frame is not
        assert o["op"] == "set" and abs(o.get("duration", by_id[o["id"]] * 1e6 / 30) - by_id[o["id"]] * 1e6 / 30) <= 1


def test_clip_without_duration_falls_back_to_the_source_span():
    assert clip_len_f({"src_in": 0.0, "src_out": 2.0, "speed": 1.0}) == 60
    assert clip_len_f({"src_in": 0.0, "src_out": 1.0, "speed": 0.5}) == 60


def test_clip_volume_is_applied_alike_by_build_qa_and_ops():
    c = {"file": "/a.mp4", "src_in": 0.0, "src_out": 1.0, "at": 0.0, "duration": 1.0, "speed": 1.0,
         "track": "video_main", "mute": False, "volume": 0.5, "gain_db": -6.0}
    want = 0.5 * 10 ** (-6 / 20)
    assert bp.clip_body("d", c, (1080, 1920))["volume"] == pytest.approx(want)
    assert qc._expected_volume(c) == pytest.approx(want) and pt._facts(c)["volume"] == pytest.approx(want)
    assert bp.clip_body("d", {**c, "mute": True}, (1080, 1920))["volume"] == 0
