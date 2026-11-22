import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pytest

import clip_clean
import lip_sync as ls
import plan_tools as pt


@pytest.mark.parametrize("fps", [24.0, 25.0, 30000 / 1001, 30.0, 60.0])
@pytest.mark.parametrize("lag", [0.0, 0.02, 0.035, 0.065, 0.08, 0.12, 0.2])
def test_audio_lead_makes_the_clean_copy_delay_whole_frames(fps, lag):
    al = ls.audio_lead_for(lag, fps)
    assert al >= 0
    lead = clip_clean.AUDIO_LEAD + al
    k = int(lead * fps + 1e-6)                       # clip_clean.make_clean's own arithmetic
    if al:
        assert abs(lead - k / fps) < 1e-6            # no sub-frame remainder: the sound is never trimmed
        assert abs(lead - (clip_clean.AUDIO_LEAD + lag)) <= 0.5 / fps + 1e-6   # within half a frame of the target


def test_audio_lead_examples():
    assert ls.audio_lead_for(0.065, 24) == pytest.approx(3 / 24 - clip_clean.AUDIO_LEAD, abs=1e-6)
    assert ls.audio_lead_for(0.0, 24) == 0.0         # the plain clean copy is already the nearest match
    assert ls.audio_lead_for(0.08, 30) == pytest.approx(4 / 30 - clip_clean.AUDIO_LEAD, abs=1e-6)


def _speechy(n, seed=1):
    rng = np.random.default_rng(seed)
    return ls._hp(np.convolve(rng.normal(size=n), np.ones(5) / 5, "same"), 40)


def test_best_offset_finds_the_clip_voice_shift():
    vo = _speechy(1000)                               # 10 s of "speech rhythm"
    clip = np.concatenate([np.zeros(150), vo[300:600]])  # the clip says VO 3.0-6.0 s, starting 1.5 s in
    # planned: clip src_in 1.2 for VO 3.0 (true answer 1.5 -> +0.3)
    d, r, margin, edge = ls.best_offset(vo, clip, 3.0, 1.2, 2.0, 1.0)
    assert d == pytest.approx(0.3, abs=0.011) and r > 0.9 and margin > 0.1 and not edge


def test_best_offset_none_without_speech():
    assert ls.best_offset(np.zeros(500), _speechy(500), 1.0, 0.0, 2.0, 1.0) is None


def test_lag_from_curves_recovers_a_known_delay():
    fps, sr = 24, 16000
    ts = np.arange(0, 6, 1 / fps)
    rng = np.random.default_rng(3)
    op = 0.2 + 0.15 * np.abs(np.convolve(rng.normal(size=len(ts)), np.ones(3) / 3, "same"))
    t = np.arange(0, 6, 1 / sr)
    loud = np.interp(t - 0.07, ts, op)                # the voice follows the mouth 70 ms later
    audio = (rng.normal(size=len(t)) * 3000 * (loud - 0.15).clip(0)).astype(np.float32)
    m = ls.lag_from_curves(ts, op, audio, sr)
    assert m and m["lag"] == pytest.approx(0.07, abs=0.011)


def _plan(tmp_path, **clip):
    f = tmp_path / "talk.mp4"; f.write_bytes(b"x")
    vo = tmp_path / "vo.wav"; vo.write_bytes(b"x")
    c = {"file": str(f), "src_in": 1.2, "src_out": 3.2, "at": 3.0, "duration": 2.0, "speed": 1.0, "mute": True,
         "lips": True, **clip}
    return {"timelines": [{"name": "T01", "vo": str(vo), "vo_in": 0.0, "clips": [c]}]}, str(f), str(vo)


def _fakes(f, vo):
    v = _speechy(1000)
    envs = {vo: v, f: np.concatenate([np.zeros(150), v[300:600]])}
    return dict(env_fn=envs.__getitem__, lag_fn=lambda p: {"lag": 0.065, "source": "lips"},
                fps_fn=lambda p: 24.0, dur_fn=lambda p: 4.5)


def test_sync_plan_moves_src_in_to_whole_frames_and_sets_audio_lead(tmp_path):
    plan, f, vo = _plan(tmp_path)
    rows = ls.sync_plan(plan, **_fakes(f, vo))
    c = plan["timelines"][0]["clips"][0]
    assert c["src_in"] == 1.5 and c["src_out"] == 3.5
    assert c["audio_lead"] == pytest.approx(ls.audio_lead_for(0.065, 24.0))
    assert rows[0]["moved_ms"] == 300 and rows[0]["lag_source"] == "lips"
    assert pt.check.__defaults__ is not None          # plan_tools still importable alongside
    assert all(pt._whole(c[k]) for k in ("src_in", "src_out"))


def test_sync_plan_keeps_an_explicit_audio_lead_and_skips_placing_own_voice(tmp_path):
    plan, f, vo = _plan(tmp_path, audio_lead=0.1, mute=False)
    rows = ls.sync_plan(plan, **_fakes(f, vo))
    c = plan["timelines"][0]["clips"][0]
    assert c["src_in"] == 1.2 and c["audio_lead"] == 0.1 and "own voice" in rows[0]["placed"]


def test_sync_plan_leaves_unmarked_clips_alone(tmp_path):
    plan, f, vo = _plan(tmp_path, lips=False)
    assert ls.sync_plan(plan, **_fakes(f, vo)) == [] and "audio_lead" not in plan["timelines"][0]["clips"][0]


AL = 3 / 24 - clip_clean.AUDIO_LEAD


def test_ops_carry_the_lip_lead():
    def plan(lead, src_in=1.0):
        c = {"file": "/v/a.mp4", "src_in": src_in, "src_out": src_in + 2, "at": 0.0, "duration": 2.0, "speed": 1.0,
             "track": "video_main", "mute": True}
        if lead:
            c["audio_lead"] = lead
        return {"timelines": [{"name": "T", "clips": [c]}]}
    dump = {"segments": [{"id": "S1", "track": "video", "source": "/v/_clean/a.mov", "src_in": 1.0, "at": 0.0}]}
    r = pt.ops(plan(0), plan(AL), "T", dump)
    assert r["ops"] == [{"op": "set", "id": "S1", "file": "/v/a.mp4", "audio_lead": AL}]
    r = pt.ops(plan(0), plan(AL, src_in=1.3), "T", dump)
    assert [o["op"] for o in r["ops"]] == ["remove", "insert"] and r["ops"][1]["audio_lead"] == AL


def test_engine_follows_the_override_and_falls_back(monkeypatch):
    monkeypatch.setenv("LIP_SYNC_ENGINE", "mediapipe")
    assert ls.engine() == "mediapipe"
    monkeypatch.delenv("LIP_SYNC_ENGINE")
    monkeypatch.setattr(ls.sys, "platform", "win32")
    monkeypatch.setattr(ls, "_mp_available", lambda: True)
    assert ls.engine() == "mediapipe"
    monkeypatch.setattr(ls, "_mp_available", lambda: False)
    assert ls.engine() is None


def test_measure_lag_without_a_tracker_uses_the_default(tmp_path, monkeypatch):
    f = tmp_path / "c.mp4"; f.write_bytes(b"x")
    monkeypatch.setattr(ls, "_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(ls, "engine", lambda: None)
    m = ls.measure_lag(str(f))
    assert m["lag"] == ls.DEFAULT_LAG and m["source"] == "default" and "mediapipe" in m["why"]


def test_measure_lag_uses_the_mediapipe_curves(tmp_path, monkeypatch):
    f = tmp_path / "c.mp4"; f.write_bytes(b"x")
    monkeypatch.setattr(ls, "_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(ls, "_openness_mediapipe", lambda p: (np.arange(0, 3, 1 / 24), np.ones(72)))
    monkeypatch.setattr(ls, "_pcm", lambda p, sr: np.zeros(sr * 3, np.float32))
    monkeypatch.setattr(ls, "lag_from_curves", lambda ts, op, a, sr=16000: {"lag": 0.06, "r": 0.8, "sharp": 0.6})
    m = ls.measure_lag(str(f), eng="mediapipe")
    assert m["lag"] == 0.06 and m["source"] == "lips" and m["engine"] == "mediapipe"


def test_a_tracker_crash_falls_back_and_is_not_cached(tmp_path, monkeypatch):
    f = tmp_path / "c.mp4"; f.write_bytes(b"x")
    monkeypatch.setattr(ls, "_cache_dir", lambda: tmp_path)
    def boom(p):
        raise RuntimeError("no model")
    monkeypatch.setattr(ls, "_openness_mediapipe", boom)
    m = ls.measure_lag(str(f), eng="mediapipe")
    assert m["source"] == "default" and "no model" in m["why"] and not list(tmp_path.glob("*.json"))
