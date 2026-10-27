import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "gui"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import checks  # noqa: E402
import folders  # noqa: E402
import capcut_project as cp  # noqa: E402
from test_capcut_project import base_draft, drafts, capcut_closed, _composed, _just_edited  # noqa: E402,F401


def test_video_folder_rule(tmp_path):
    for d in ("Nativia", "docs", "_practice/run1", ".git", "PYNK_AI_UGC_Studio", "Uvola Cereza Ácida/.edit-mo-to"):
        (tmp_path / d).mkdir(parents=True)
    (tmp_path / "Uvola Cereza Ácida/.edit-mo-to/job.json").write_text("{}", encoding="utf-8")
    (tmp_path / "loose.txt").write_text("x")
    found = folders.video_folders(tmp_path)
    assert sorted(f["name"] for f in found) == ["Nativia", "Uvola Cereza Ácida", "run1"]
    by = {f["name"]: f for f in found}
    assert [n for n, f in by.items() if f["has_job"]] == ["Uvola Cereza Ácida"]
    assert [n for n, f in by.items() if f["practice"]] == ["run1"]
    assert Path(by["Nativia"]["path"]) == tmp_path / "Nativia"


def test_safe_path_blocks_escape(tmp_path):
    root = tmp_path / "root"
    (root / "Uvola Cereza Ácida/refs").mkdir(parents=True)
    ok = folders.safe_path(root / "Uvola Cereza Ácida/refs/a.pdf", [root])
    assert ok == (root / "Uvola Cereza Ácida/refs/a.pdf").resolve()
    with pytest.raises(PermissionError):
        folders.safe_path(root / "../x", [root])
    with pytest.raises(PermissionError):
        folders.safe_path("Z:/elsewhere/x" if sys.platform == "win32" else "/etc/passwd", [root])


def test_safe_path_case_insensitive_on_windows(tmp_path):
    root = tmp_path / "Root"
    root.mkdir()
    if sys.platform == "win32":
        assert folders.safe_path(str(root).upper() + "\\a", [root])
    else:
        with pytest.raises(PermissionError):
            folders.safe_path(str(root).upper() + "/a", [root])


def test_setup_shape(monkeypatch, tmp_path):
    import machine
    monkeypatch.setitem(machine.PATHS, "capcut_drafts", str(tmp_path))
    monkeypatch.setitem(machine.PATHS, "mcp_servers", str(tmp_path))
    (tmp_path / "capcut-start.mjs").write_text("")
    res = checks.setup()
    assert [r["name"] for r in res] == ["Python venv", "ffmpeg", "ffprobe", "CapCut drafts folder", "CapCut MCP launcher"]
    assert all(set(r) == {"name", "ok", "detail"} for r in res)
    by = {r["name"]: r for r in res}
    assert by["CapCut drafts folder"]["ok"] and by["CapCut MCP launcher"]["ok"]


def test_setup_failures_do_not_raise(monkeypatch, tmp_path):
    import machine
    monkeypatch.setitem(machine.PATHS, "capcut_drafts", str(tmp_path / "nope"))
    monkeypatch.setitem(machine.PATHS, "mcp_servers", str(tmp_path / "nope"))
    monkeypatch.setitem(machine.PATHS, "python", str(tmp_path / "nopython"))
    monkeypatch.setattr(checks.shutil, "which", lambda n: None)
    res = {r["name"]: r for r in checks.setup()}
    assert not any(r["ok"] for r in res.values())
    assert all(r["detail"] for r in res.values())


def test_capcut_running_delegates(monkeypatch):
    monkeypatch.setattr(cp, "_capcut_running", lambda: True)
    assert checks.capcut_running() is True


def test_temp_en_timelines(tmp_path, drafts):
    target = _composed(tmp_path, drafts)
    assert checks.temp_en_timelines(target) == []
    tl = cp.list_timelines(target)[1]
    f = cp._content_file(target / "Timelines" / tl["id"])
    c = json.loads(f.read_text(encoding="utf-8"))
    c["tracks"].append({"name": "TEMP_EN_delete_me", "type": "text", "segments": [
        {"id": "s1", "material_id": "none", "target_timerange": {"start": 0, "duration": 1000000}}]})
    f.write_text(json.dumps(c), encoding="utf-8")
    _just_edited(f)
    assert checks.temp_en_timelines(target) == [tl["name"]]
