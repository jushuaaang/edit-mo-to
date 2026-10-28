import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "gui"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import adapters  # noqa: E402
import media_timing as mt  # noqa: E402


def _check_table(t, n):
    assert t["title"] and t["columns"]
    assert len(t["rows"]) == n
    for r in t["rows"]:
        assert len(r["cells"]) == len(t["columns"])
        assert all(isinstance(c, str) for c in r["cells"])
        assert r["status"] in ("ok", "wait", "you", "err", "opt", "mute", None)


def test_adapters_registry():
    assert set(adapters.ADAPTERS) == {"timings", "cuts", "qa", "clips", "prompts"}


def test_qa_adapter_status_map():
    data = {"rows": [
        {"n": 1, "check": "present", "status": "PASS", "evidence": "ok", "fix": "", "timeline": "A"},
        {"n": 2, "check": "reuse", "status": "FAIL", "evidence": "clip 3 reused", "fix": "swap", "timeline": "A"},
        {"n": 3, "check": "temp_en", "status": "OPEN", "evidence": "TEMP_EN present", "fix": "delete", "timeline": "B"},
    ], "passed": 1, "verdict": "FAIL (1 issues)"}
    t = adapters.ADAPTERS["qa"](data)
    _check_table(t, 3)
    assert [r["status"] for r in t["rows"]] == ["ok", "err", "you"]
    assert "FAIL (1 issues)" in t["title"]


def test_timings_adapter_marks_unmatched():
    words = [{"word": w, "start": i * 0.4, "end": i * 0.4 + 0.3}
             for i, w in enumerate("meet nativia the vitamin i never skip".split())]
    lines = ["Meet Nativia the vitamin I never skip", "Totally unrelated sentence about oranges"]
    rows = mt.align_lines(words, lines)
    assert [r["matched"] for r in rows] == [True, False]
    t = adapters.ADAPTERS["timings"]({"words": words, "total": "2:24", "lines": rows})
    _check_table(t, 2)
    assert [r["status"] for r in t["rows"]] == ["ok", "err"]
    assert rows[0]["start_sf"] in t["rows"][0]["cells"]


def test_clips_adapter():
    data = {"batch": "b1", "clips": [
        {"file": "V01.mp4", "match": {"name": "V01_L01", "score": 0.9}, "status": "PASS", "flags": []},
        {"file": "x.mp4", "match": {"name": None, "why": "no match"}, "status": "FLAG",
         "flags": ["duplicate of V01.mp4", "text 'HI'"], "action": "-> _rejected/x.mp4"}]}
    t = adapters.ADAPTERS["clips"](data)
    _check_table(t, 2)
    assert [r["status"] for r in t["rows"]] == ["ok", "err"]
    assert "duplicate of V01.mp4" in t["rows"][1]["cells"][-1]


def test_cuts_adapter():
    data = {"media": "a.mp4", "duration": 10.0, "words": [], "candidates": [
        {"id": "c001", "type": "pause", "cut": [1.0, 1.5], "recommend": "cut", "note": "pause 0.50s -> 0.10s"},
        {"id": "c002", "type": "retake", "cut": [3.0, 4.2], "recommend": "review", "removes": "so I", "keeps": "so I think"}]}
    t = adapters.ADAPTERS["cuts"](data)
    _check_table(t, 2)
    assert [r["id"] for r in t["rows"]] == ["c001", "c002"]
    assert [r["status"] for r in t["rows"]] == ["ok", "you"]
    assert "1:00" in t["rows"][0]["cells"]


def test_prompts_adapter():
    data = {"prompts": [
        {"id": "AI-1", "line": 1, "vo_in_f": 0, "vo_out_f": 120, "gen_len_s": 4, "setting": "bathroom",
         "subject": "woman", "action": "smiles", "dialogue": "Meet Nativia"},
        {"id": "AI-2", "line": 2, "gen_len_s": 4, "subject": "same woman"}]}
    t = adapters.ADAPTERS["prompts"](data)
    _check_table(t, 2)
    assert [r["id"] for r in t["rows"]] == ["AI-1", "AI-2"]


def test_prompt_rows_carry_the_prompt_the_chat_shows():
    """Copy prompt must copy the real prompt: the fenced block render_prompts puts in chat for that id."""
    import plan_tools as pt
    spec = {"style": "ugc", "mode": "seedance", "generator": "seedance",
            "attach": {"@Image1": "refs/host.png"},
            "locks": {"notext": "NO TEXT LOCK: no captions anywhere in frame."},
            "prompts": [
                {"id": "AI-1", "line": 1, "vo_in_f": 0, "vo_out_f": 120, "gen_len_s": 4, "setting": "bathroom",
                 "subject": "woman", "action": "she smiles", "camera": "selfie", "dialogue": "Meet Nativia",
                 "attach": ["@Image1"], "locks": ["notext"], "negative": "no extra people"},
                {"id": "C-1", "kind": "client", "line": 2, "file": "host_take3.mp4", "in_f": 0, "out_f": 60,
                 "vo_in_f": 120, "vo_out_f": 180},
                {"id": "SB-1", "kind": "keyframe", "line": 1, "subject": "jar on a counter", "look": "warm"}]}
    t = adapters.ADAPTERS["prompts"](spec)
    _check_table(t, 3)
    rows = {r["id"]: r for r in t["rows"]}
    chat = pt.render_prompts(spec, ["Meet Nativia", "Two a day"], None)
    for pid in ("AI-1", "SB-1"):
        assert rows[pid]["prompt"] == pt._block(spec, next(p for p in spec["prompts"] if p["id"] == pid))
        assert f"**{pid}**\n```\n{rows[pid]['prompt']}\n```" in chat
    assert rows["AI-1"]["prompt"].startswith("Start on @Image1.") and "NO TEXT LOCK" in rows["AI-1"]["prompt"]
    assert rows["C-1"]["prompt"] is None  # a picked client clip has no prompt to copy
    hf = {**spec, "mode": "prompts", "generator": "higgsfield", "generator_model": "seedance-2.5"}
    t = adapters.ADAPTERS["prompts"](hf)
    ai = next(r for r in t["rows"] if r["id"] == "AI-1")
    assert ai["prompt"] == pt._block(hf, hf["prompts"][0]) == rows["AI-1"]["prompt"]   # same text as old "seedance"


def test_clip_rows_carry_sheet_and_match_name():
    data = {"batch": "b1", "images": "/tmp/qc/b1", "clips": [
        {"file": "flow 01.mp4", "match": {"name": "V01_L01", "score": 0.9}, "status": "FLAG", "flags": ["text 'HI'"]},
        {"file": "x.mov", "match": {"name": None, "why": "no match"}, "status": "FLAG", "flags": ["no match"]}]}
    t = adapters.ADAPTERS["clips"](data)
    _check_table(t, 2)
    a, b = t["rows"]
    assert a["match"] == "V01_L01" and a["sheet"] == "/tmp/qc/b1/flow 01_sheet.jpg"
    assert b["match"] is None and b["sheet"] == "/tmp/qc/b1/x_sheet.jpg"
    assert adapters.ADAPTERS["clips"]({"clips": data["clips"]})["rows"][0]["sheet"] is None  # no images folder
