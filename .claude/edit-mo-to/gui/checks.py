"""Read-only facts for the GUI: the setup check, whether CapCut is open, which timelines still carry the
TEMP_EN_delete_me review track. Never changes a CapCut project.

    setup() -> [{"name","ok","detail"}]
    capcut_running() -> bool
    temp_en_timelines(project_dir) -> [timeline name, ...] in the project's own order
"""
import shutil
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import capcut_project  # noqa: E402
import machine  # noqa: E402

TEMP_EN_TRACK = "TEMP_EN_delete_me"
TIMEOUT = 5


def _entry(name: str, ok: bool, detail: str) -> dict:
    return {"name": name, "ok": bool(ok), "detail": detail}


def _run_version(name: str, cmd: list[str]) -> dict:
    """Run `cmd` (a version command); ok when it exits 0. Never raises."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError) as e:
        return _entry(name, False, str(e) or type(e).__name__)
    lines = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
    first = lines[0] if lines else ""
    if r.returncode != 0:
        return _entry(name, False, first or f"exit code {r.returncode}")
    return _entry(name, True, first or "ok")


def _path_check(name: str, p: Path, is_dir: bool) -> dict:
    ok = p.is_dir() if is_dir else p.is_file()
    return _entry(name, ok, str(p) if ok else f"not found: {p}")


def _tool(name: str) -> dict:
    exe = shutil.which(name)
    if not exe:
        return _entry(name, False, f"{name} not found on PATH")
    return _run_version(name, [exe, "-version"])


def setup() -> list[dict]:
    paths = machine.PATHS  # read at call time so tests can patch it
    return [
        _run_version("Python venv", [str(paths["python"]), "--version"]),
        _tool("ffmpeg"),
        _tool("ffprobe"),
        _path_check("CapCut drafts folder", Path(paths["capcut_drafts"]), True),
        _path_check("CapCut MCP launcher", Path(paths["mcp_servers"]) / "capcut-start.mjs", False),
    ]


def capcut_running() -> bool:
    return capcut_project._capcut_running()


def temp_en_timelines(project_dir: Path) -> list[str]:
    """Names of timelines that still have a TEMP_EN_delete_me track, in the project's own order (read-only).

    Never raises on bad data: a missing or unreadable project (project.json / content file) gives [],
    and a single timeline whose content file is missing or unreadable is skipped."""
    project = Path(project_dir)
    found = []
    try:
        timelines = capcut_project.list_timelines(project)
    except (OSError, ValueError, KeyError):
        return []
    for tl in timelines:
        try:
            segs = capcut_project.segments(project, tl["name"])["segments"]
        except (OSError, ValueError, KeyError):
            continue
        if any(s.get("track") == TEMP_EN_TRACK for s in segs):
            found.append(tl["name"])
    return found
