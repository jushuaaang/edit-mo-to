"""Which folders under the root are videos, and whether a path may be served. Read-only.

    video_folders(root) -> [{"name","path","has_job","practice"}]
    is_video_folder(path, root) -> bool   the same rule for one path (which need not exist yet)
    safe_path(p, roots) -> resolved Path, or PermissionError when p is outside every root
"""
import os
from pathlib import Path

SKIP_NAMES = {"docs", "PYNK_AI_UGC_Studio"}
JOB_FILE = Path(".edit-mo-to") / "job.json"


def _subfolders(parent: Path) -> list[Path]:
    try:
        return sorted(p for p in parent.iterdir() if p.is_dir())
    except OSError:
        return []


def _entry(p: Path, practice: bool) -> dict:
    return {"name": p.name, "path": str(p), "has_job": (p / JOB_FILE).is_file(), "practice": practice}


def video_folders(root: Path) -> list[dict]:
    """Direct subfolders of root (not starting with . or _, not docs / PYNK_AI_UGC_Studio), plus each
    root/_practice/<name>/ flagged practice."""
    root = Path(root)
    out = [_entry(p, False) for p in _subfolders(root) if _video_name(p.name, False)]
    out += [_entry(p, True) for p in _subfolders(root / "_practice") if _video_name(p.name, True)]
    return out


def _video_name(name: str, practice: bool) -> bool:
    if practice:
        return not name.startswith(".")
    return not name.startswith((".", "_")) and name not in SKIP_NAMES


def is_video_folder(path: "str | Path", root: "str | Path") -> bool:
    """True when path (resolved) is a direct video subfolder of root, or root/_practice/<name>, by the
    video_folders rule. The folder itself need not exist."""
    try:
        p, r = Path(path).resolve(), Path(root).resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    parent = _key(p.parent)
    if parent == _key(r):
        return _video_name(p.name, False)
    if parent == _key(r / "_practice"):
        return _video_name(p.name, True)
    return False


def _key(p: Path) -> str:
    return os.path.normcase(str(p))


def safe_path(p: "str | Path", roots: list[Path]) -> Path:
    """Resolve p (symlinks, junctions, ..) and return it if it sits inside one of roots; else PermissionError.
    Compared case-insensitively on Windows; a path on another drive is never inside a root."""
    try:
        resolved = Path(p).resolve()
    except (OSError, RuntimeError, ValueError) as e:
        raise PermissionError(f"path not allowed: {p}") from e
    for r in roots:
        root = Path(r).resolve()
        if os.path.splitdrive(_key(resolved))[0] != os.path.splitdrive(_key(root))[0]:
            continue
        rk = _key(root).rstrip("\\/")
        pk = _key(resolved)
        if pk == rk or pk.startswith(rk + os.sep):
            return resolved
    raise PermissionError(f"path not allowed: {p}")
