import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "gui"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import checks  # noqa: E402
import folders  # noqa: E402
import capcut_project as cp  # noqa: E402
import hashlib  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402


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
        folders.safe_path(_other_drive_path(root), [root])


def _other_drive_path(root: Path) -> str:
    if sys.platform != "win32":
        return "/etc/passwd"
    used = os.path.splitdrive(str(root.resolve()))[0].upper()
    letter = next(c for c in "QRSTUVWXYZ" if c + ":" != used)
    return f"{letter}:/elsewhere/x"


def test_safe_path_unc_blocked(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(PermissionError):
        folders.safe_path("//server/share/x", [root])


def test_safe_path_prefix_confusion(tmp_path):
    root = tmp_path / "root"
    sibling = tmp_path / "root2"
    root.mkdir()
    sibling.mkdir()
    (sibling / "a.txt").write_text("x")
    with pytest.raises(PermissionError):
        folders.safe_path(sibling / "a.txt", [root])
    with pytest.raises(PermissionError):
        folders.safe_path(sibling, [root])
    assert folders.safe_path(root, [root]) == root.resolve()


def _link_dir(link: Path, target: Path) -> bool:
    try:
        os.symlink(target, link, target_is_directory=True)
        return True
    except (OSError, NotImplementedError):
        pass
    if sys.platform == "win32":
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
        return r.returncode == 0 and link.exists()
    return False


def test_safe_path_link_escape(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("x")
    if not _link_dir(root / "link", outside):
        pytest.skip("cannot create a symlink or junction here")
    with pytest.raises(PermissionError):
        folders.safe_path(root / "link" / "secret.txt", [root])


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


def _timeline(project: Path, tid: str, with_temp: bool, readable: bool = True) -> None:
    folder = project / "Timelines" / tid
    folder.mkdir(parents=True)
    f = folder / "draft_info.json"
    if not readable:
        f.write_text("{not json", encoding="utf-8")
        return
    tracks = [{"name": "main", "type": "video", "segments": [
        {"id": tid + "v", "material_id": "m", "target_timerange": {"start": 0, "duration": 1000000}}]},
        {"name": "subs", "type": "text", "segments": []}]
    if with_temp:
        tracks.append({"name": "TEMP_EN_delete_me", "type": "text", "segments": [
            {"id": tid + "t", "material_id": "none", "target_timerange": {"start": 0, "duration": 1000000}}]})
    f.write_text(json.dumps({"id": tid, "duration": 1000000, "tracks": tracks, "materials": {"videos": [
        {"id": "m", "path": "x.mp4", "width": 1080, "height": 1920}]}}), encoding="utf-8")


def _project(tmp_path: Path, spec: list) -> Path:
    """spec: [(name, with_temp, readable)] -> a project in the Timelines/ layout, in that order."""
    project = tmp_path / "Proj"
    (project / "Timelines").mkdir(parents=True)
    tls = []
    for n, (name, temp, ok) in enumerate(spec, 1):
        tid = f"tid-{n}"
        _timeline(project, tid, temp, ok)
        tls.append({"id": tid, "name": name})
    (project / "Timelines" / "project.json").write_text(
        json.dumps({"main_timeline_id": "tid-1", "timelines": tls}), encoding="utf-8")
    return project


def _hashes(root: Path) -> dict:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def test_temp_en_timelines(tmp_path):
    project = _project(tmp_path, [("Zeta", True, True), ("Clean", False, True),
                                  ("Alpha", True, True), ("Broken", True, False)])
    before = _hashes(project)
    assert checks.temp_en_timelines(project) == ["Zeta", "Alpha"]  # project order, broken one skipped
    assert _hashes(project) == before


def test_temp_en_timelines_none(tmp_path):
    assert checks.temp_en_timelines(_project(tmp_path, [("A", False, True)])) == []


def test_temp_en_timelines_bad_project_gives_empty(tmp_path):
    assert checks.temp_en_timelines(tmp_path / "missing") == []
    project = _project(tmp_path, [("A", True, True)])
    (project / "Timelines" / "project.json").write_text("{oops", encoding="utf-8")
    assert checks.temp_en_timelines(project) == []
