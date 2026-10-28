"""`--out <path>` on the tools the workflow docs used to redirect with `>`: the JSON goes to the file (its folder is
created), stdout gets a short {"saved": path}; without --out the full JSON still goes to stdout."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import capcut_project  # noqa: E402
import edit_diff  # noqa: E402
import qa_check  # noqa: E402
import sheets  # noqa: E402

RES = {"rows": [], "passed": 3, "verdict": "PASS", "note": "é"}


def _plan(tmp_path):
    p = tmp_path / "plan.json"
    p.write_text("{}", encoding="utf-8")
    return p


def _out(capsys):
    return json.loads(capsys.readouterr().out)


def test_qa_check_build_out(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(qa_check, "check_build", lambda *a, **k: dict(RES))
    out = tmp_path / "new" / "deeper" / "qa_check.json"
    qa_check.main(["build", str(_plan(tmp_path)), "proj", "--search", str(tmp_path), "--out", str(out)])
    assert json.loads(out.read_text(encoding="utf-8")) == RES
    printed = _out(capsys)
    assert printed["saved"] == str(out) and printed["verdict"] == "PASS" and "rows" not in printed


def test_qa_check_build_without_out_prints(tmp_path, monkeypatch, capsys):
    seen = {}

    def fake(*a, **k):
        seen["search"] = k.get("search")
        return dict(RES)
    monkeypatch.setattr(qa_check, "check_build", fake)
    qa_check.main(["build", str(_plan(tmp_path)), "proj", "--search", str(tmp_path)])
    assert _out(capsys) == RES and seen["search"] == [str(tmp_path)]


def test_qa_check_fail_still_exits_1_with_out(tmp_path, monkeypatch):
    monkeypatch.setattr(qa_check, "check_build", lambda *a, **k: {**RES, "verdict": "FAIL (1 issues)"})
    out = tmp_path / "q" / "qa.json"
    with pytest.raises(SystemExit) as e:
        qa_check.main(["build", str(_plan(tmp_path)), "proj", "--out", str(out)])
    assert e.value.code == 1 and out.exists()


def test_qa_check_captions_out(tmp_path, monkeypatch, capsys):
    import captions as cap
    script, timings = tmp_path / "s.txt", tmp_path / "t.json"
    script.write_text("hola\n", encoding="utf-8")
    timings.write_text('{"words": []}', encoding="utf-8")
    monkeypatch.setattr(cap, "caption_inputs", lambda plan, tl, s, t: (str(script), str(timings)))
    monkeypatch.setattr(qa_check, "check_captions", lambda *a, **k: dict(RES))
    out = tmp_path / "c" / "qa_captions_T1.json"
    qa_check.main(["captions", str(_plan(tmp_path)), "proj", "T1", "--out", str(out)])
    assert json.loads(out.read_text(encoding="utf-8")) == RES and _out(capsys)["saved"] == str(out)


def test_sheets_inventory_out_creates_the_folder(tmp_path, monkeypatch, capsys):
    seen = {}

    def fake(folder, out_dir, mx):
        seen["args"] = (folder, out_dir, mx)
        return {"clips": [{"n": 1}], "skipped": [], "sheets": []}
    monkeypatch.setattr(sheets, "inventory", fake)
    out = tmp_path / "reports" / "job" / "inv" / "inventory.json"
    sheets.main(["inventory", str(tmp_path / "broll"), str(tmp_path / "reports" / "job" / "inv"), "--max", "5",
                 "--out", str(out)])
    assert json.loads(out.read_text(encoding="utf-8"))["clips"] == [{"n": 1}]
    assert seen["args"] == (tmp_path / "broll", tmp_path / "reports" / "job" / "inv", 5)
    assert _out(capsys)["saved"] == str(out)


def test_sheets_inventory_without_out_prints(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sheets, "inventory", lambda f, o, m: {"clips": [], "skipped": [], "sheets": []})
    sheets.main(["inventory", str(tmp_path), str(tmp_path / "inv")])
    assert _out(capsys) == {"clips": [], "skipped": [], "sheets": []}


def test_edit_diff_out(tmp_path, monkeypatch, capsys):
    built = tmp_path / "built.json"
    built.write_text('{"segments": []}', encoding="utf-8")
    monkeypatch.setattr(capcut_project, "segments", lambda *a, **k: {"segments": []})
    out = tmp_path / "d" / "diff_T1.json"
    edit_diff.main(["diff", str(built), "proj", "T1", "--out", str(out)])
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert "patterns" in saved and _out(capsys)["saved"] == str(out)
    edit_diff.main(["diff", str(built), "proj", "T1"])
    assert "patterns" in _out(capsys)


def test_capcut_segments_out(tmp_path, monkeypatch, capsys):
    seen = {}

    def fake(project, timeline, folders):
        seen["folders"] = folders
        return [{"track": "video", "n": 1}]
    monkeypatch.setattr(capcut_project, "segments", fake)
    out = tmp_path / "s" / "seg_T1.json"
    capcut_project.main(["segments", "proj", "T1", str(tmp_path), "--out", str(out)])
    assert json.loads(out.read_text(encoding="utf-8")) == [{"track": "video", "n": 1}]
    assert seen["folders"] == [tmp_path] and _out(capsys)["saved"] == str(out)
    capcut_project.main(["segments", "proj", "T1"])
    assert _out(capsys) == [{"track": "video", "n": 1}]
