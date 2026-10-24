"""Build and extend multi-timeline CapCut projects from VectCutAPI drafts.

VectCutAPI writes single-timeline drafts (capcut_legacy profile, draft_info.json).
CapCut 9.x stores extra timelines as:
    <project>/Timelines/project.json            timeline list + main_timeline_id
    <project>/Timelines/<id>/draft_info.json     one per timeline (+ draft_content.json)
    <project>/draft_info.json                    copy of the main timeline
Verified opening in CapCut 9.6 on 2026-10-15.

CLI (prints JSON):
    compose <target> "Name=draft_dir" ...        new project; first entry is the main timeline
                                                 (timelines use the imported ORIGINAL files, listed in
                                                 CapCut's media panel; --keep-copies keeps VectCutAPI copies)
    import <project> <file> ...                  add files to the project's media panel (CapCut Import list)
    link-originals <project> [search_dir ...]    point timelines at the original files instead of hashed
                                                 copies in assets/, import them, delete unused copies
    add-timeline <project> <name> <draft_dir>    append a timeline built from a new draft
    duplicate <project> <source_name> <new_name> copy an existing (maybe hand-edited) timeline
    replace <project> <name> <draft_dir>         edit a timeline in place (auto-backup, keeps its id)
    add-tracks <project> <name> <draft_dir> [audio]  merge a draft's audio (music) into a timeline,
                                                 keeping captions and hand edits (auto-backup)
    add-overlay <project> <name> <draft_dir> [track] add a draft's video segments (B-roll) onto a timeline's
                                                 video_overlay (or named) track, keeping captions and hand
                                                 edits byte-for-byte (auto-backup, refuses overlaps)
    patch <project> <name> <ops.json>            edit a (hand-edited) timeline in place, op by op: set / remove /
                                                 insert / split / ripple / transition / grade, segments by their CapCut id;
                                                 everything else stays byte-for-byte (auto-backup, writes
                                                 draft_content.json, validates before writing; --dry-run)
    segments <project> <name> [search_dir ...]   list what's on a timeline (layout, text, original files);
                                                 search_dirs help find sources CapCut forgot
    backup <project> <name>                      back up a timeline
    list <project>
    wait <draft_dir> [timeout_s]                 wait for an async VectCutAPI save
"""
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from machine import PATHS

CONTENT_FILES = ("draft_info.json", "draft_content.json")
TIMELINE_EXTRAS = ("template-2.tmp", "attachment_editing.json", "attachment_pc_common.json")
BACKUP_DIR = "edit-mo-to-backups"
BUSY_WINDOW_S = 10
STAMP_FILE = ".edit-mo-to-last-write"
# CapCut 9.6 rewrites media inside the project folder as <placeholder>/assets/... when it saves.
PLACEHOLDER_RE = re.compile(r"##_draftpath_placeholder_[0-9A-Fa-f-]+_##")
FULL_FRAME_CROP = {"upper_left_x": 0.0, "upper_left_y": 0.0, "upper_right_x": 1.0, "upper_right_y": 0.0,
                   "lower_left_x": 0.0, "lower_left_y": 1.0, "lower_right_x": 1.0, "lower_right_y": 1.0}
MIN_ARGS = {"import": 2, "link-originals": 1, "compose": 2, "add-timeline": 3, "duplicate": 3, "replace": 3, "add-tracks": 3, "add-overlay": 3,
            "patch": 3, "segments": 2, "backup": 2, "list": 1, "wait": 1}
PHOTO_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
PHOTO_DURATION_US = 10_800_000_000  # what CapCut stores as a still's material duration (3 h)
# Per-segment helper materials CapCut gives every video segment (extra_material_refs). add-overlay clones
# these from a segment already on the target track, so the new clip has the same shape CapCut saves.
COMPANION_KINDS = ("speeds", "canvases", "placeholder_infos", "sound_channel_mappings", "material_colors",
                   "vocal_separations")

# Colour-grade sliders (CapCut's Adjustment panel): one materials.effects entry per slider, copied from
# what CapCut 9.6 saved in the editor's project "1003" (slider -100..100 is stored as value -1..1; the
# effect files are the shared "adjust" resource in CapCut's cache). Only properties seen in a real
# project are supported; "version" is what CapCut wrote for each one.
GRADE_VERSIONS = {"brightness": "v2", "contrast": "v3", "saturation": "v1", "temperature": "v3"}
GRADE_ORDER = ("brightness", "contrast", "saturation", "highlight", "white", "black", "temperature", "tone",
               "light_sensation")  # the order CapCut lists them in extra_material_refs
GRADE_CACHE = PATHS["capcut_grade_cache"]  # per machine: machine.json "capcut_grade_cache"


class ProjectBusy(RuntimeError):
    """The project was modified seconds ago; CapCut probably has it open."""


class DraftSaveFailed(RuntimeError):
    """VectCutAPI said it saved, but the draft folder never appeared."""


def _now_us() -> int:
    return int(time.time() * 1_000_000)


def _new_id() -> str:
    return str(uuid.uuid4()).upper()


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _content_file(folder: Path) -> Path:
    """The newest content file. CapCut 9.6 saves into draft_content.json only, so after the user
    edits (captions, trims) draft_info.json is stale; ties go to draft_content.json."""
    found = [folder / n for n in reversed(CONTENT_FILES) if (folder / n).exists()]
    if not found:
        raise FileNotFoundError(f"no draft content in {folder}")
    return max(found, key=lambda f: f.stat().st_mtime)


def _write_root(project: Path, content: dict) -> None:
    """The project root keeps a copy of the main timeline in both content files."""
    for name in CONTENT_FILES:
        _write(project / name, content)


class _RawFloat(float):
    """A float that remembers how it was written, so re-saving CapCut's JSON keeps its exact digits."""

    def __new__(cls, text):
        obj = super().__new__(cls, text)
        obj.raw = text if isinstance(text, str) else repr(float(text))
        return obj


def _read_exact_text(text: str) -> dict:
    return json.loads(text, parse_float=_RawFloat)


def _read_exact(path: Path) -> dict:
    return _read_exact_text(path.read_text(encoding="utf-8"))


def _dump_exact(node) -> str:
    """Compact JSON as CapCut writes it; with _read_exact, untouched content comes back byte-for-byte."""
    if isinstance(node, _RawFloat):
        return node.raw
    if isinstance(node, dict):
        return "{" + ",".join(json.dumps(k, ensure_ascii=False) + ":" + _dump_exact(v) for k, v in node.items()) + "}"
    if isinstance(node, list):
        return "[" + ",".join(_dump_exact(v) for v in node) + "]"
    return json.dumps(node, ensure_ascii=False)


def _write_newest_content(folder: Path, data: dict) -> None:
    """Write both content files, leaving draft_content.json strictly the newer one, so _content_file
    never picks draft_info.json (which CapCut 9.6 lets go stale) over it."""
    text = _dump_exact(data)
    for name in CONTENT_FILES:  # draft_info.json first
        (folder / name).write_text(text, encoding="utf-8")
    newest = (folder / "draft_content.json").stat().st_mtime_ns
    os.utime(folder / "draft_info.json", ns=(newest - 1_000_000_000, newest - 1_000_000_000))


def _rewrite_media_paths(node, project: Path, final: Path | None = None) -> None:
    """Point draft media paths at <final>/assets/... (final defaults to project).

    Only rewrites when the file really exists under <project>/assets/, so the user's own
    media that merely lives in some folder called 'assets' is never redirected."""
    final = final or project
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "path" and isinstance(value, str) and "/assets/" in value.replace("\\", "/"):
                rel = value.replace("\\", "/").split("/assets/", 1)[1]
                if (project / "assets" / rel).exists():
                    node[key] = final.as_posix() + "/assets/" + rel
            else:
                _rewrite_media_paths(value, project, final)
    elif isinstance(node, list):
        for value in node:
            _rewrite_media_paths(value, project, final)


def _probe_video(path: str) -> tuple[int, int, int] | None:
    """(coded width, coded height, rotation degrees) of a video file, or None if ffprobe can't read it."""
    import subprocess

    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                              "stream=width,height:stream_side_data=rotation", "-of", "json", path],
                             capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
        stream = json.loads(out.stdout)["streams"][0]
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, IndexError):
        return None
    rot = next((int(d["rotation"]) for d in stream.get("side_data_list", []) if "rotation" in d), 0)
    return int(stream["width"]), int(stream["height"]), rot


def _fix_rotated_sizes(content: dict) -> tuple[list[dict], list[str]]:
    """Store ±90° rotated clips (phone .MOVs) at their upright size, as CapCut 9.6 does when it imports
    them itself (e.g. 2160x3840, clip rotation 0). VectCutAPI stores the coded landscape size instead.
    Returns (fixed, unchecked): unchecked clips couldn't be probed and need a look in CapCut."""
    fixed, unchecked = [], []
    for m in content.get("materials", {}).get("videos", []):
        if not isinstance(m, dict) or m.get("type") != "video":
            continue
        src = m.get("remote_url") or m.get("path") or ""
        info = _probe_video(src) if src else None
        if info is None:
            unchecked.append(src)
            continue
        w, h, rot = info
        if rot % 180 and (m.get("width"), m.get("height")) == (w, h):
            m["width"], m["height"] = h, w
            fixed.append({"source": src, "rotation": rot, "size": f"{h}x{w}"})
    return fixed, unchecked


def _placeholder(project: Path, first: Path | None = None) -> str | None:
    """The project's CapCut path placeholder, if CapCut has saved it (searched in `first` first)."""
    files = ([first] if first else []) + [project / "draft_content.json"]
    files += sorted((project / "Timelines").glob("*/draft_content.json"))
    for f in files:
        if f.exists():
            found = PLACEHOLDER_RE.search(f.read_text(encoding="utf-8"))
            if found:
                return found.group(0)
    return None


def _capcut_running() -> bool:
    import subprocess

    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq CapCut.exe", "/NH"],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "capcut.exe" in out.lower()


def _validate_name(name: str) -> None:
    bad = set('<>:"/\\|?*')
    if not name.strip() or any(ch in bad for ch in name):
        raise ValueError(f"{name!r} can't be a CapCut project/timeline name (no <>:\"/\\|?* characters)")


def _newest_mtime(project: Path) -> float:
    candidates = [project / n for n in CONTENT_FILES] + [project / "Timelines" / "project.json"]
    candidates += list((project / "Timelines").glob("*/draft_*.json"))
    return max((p.stat().st_mtime for p in candidates if p.exists()), default=0)


def _mark_own_write(project: Path) -> None:
    """Remember our latest write so it isn't mistaken for CapCut touching the project."""
    (project / STAMP_FILE).write_text(repr(_newest_mtime(project)), encoding="utf-8")


def _check_not_busy(project: Path) -> None:
    if _capcut_running():
        raise ProjectBusy("CapCut is running; quit CapCut completely before changing a project "
                          "(it rewrites the project when it closes and would drop our changes)")
    newest = _newest_mtime(project)
    stamp = project / STAMP_FILE
    ours = float(stamp.read_text(encoding="utf-8")) if stamp.exists() else -1
    if newest > ours and time.time() - newest < BUSY_WINDOW_S:
        raise ProjectBusy(f"{project.name} was modified in the last {BUSY_WINDOW_S}s; close it in CapCut first")


def _write_timeline(project: Path, content: dict, extras_from: Path) -> Path:
    folder = project / "Timelines" / content["id"]
    folder.mkdir(parents=True)
    for name in CONTENT_FILES:
        _write(folder / name, content)
    for name in TIMELINE_EXTRAS:
        if (extras_from / name).exists():
            shutil.copy2(extras_from / name, folder / name)
    return folder


def _import_draft(project: Path, draft: Path, final: Path | None = None) -> tuple[dict, dict]:
    """Copy a draft's media into the project; return its content with paths, id and rotated clip
    sizes fixed, plus a report {rotation_fixed, rotation_unchecked}."""
    if (draft / "assets").exists():
        shutil.copytree(draft / "assets", project / "assets", dirs_exist_ok=True)
    content = _read(_content_file(draft))
    _rewrite_media_paths(content, project, final)
    content["id"] = _new_id()
    fixed, unchecked = _fix_rotated_sizes(content)
    return content, {"rotation_fixed": fixed, "rotation_unchecked": unchecked}


def _ensure_new_name(project: Path, name: str) -> None:
    _validate_name(name)
    if any(t["name"] == name for t in list_timelines(project)):
        raise ValueError(f"{project.name} already has a timeline named {name!r}; pick another name")


def _project_json(project: Path) -> dict:
    return _read(project / "Timelines" / "project.json")


def _save_project_json(project: Path, pj: dict) -> None:
    pj["update_time"] = _now_us()
    _write(project / "Timelines" / "project.json", pj)
    _mark_own_write(project)


def _timeline_entry(name: str, tid: str) -> dict:
    now = _now_us()
    return {"create_time": now, "id": tid, "is_marked_delete": False, "name": name, "update_time": now}


def _find(project: Path, name: str) -> dict:
    for t in list_timelines(project):
        if t["name"] == name:
            return t
    raise KeyError(f"no timeline named {name!r} in {project.name}; have {[t['name'] for t in list_timelines(project)]}")


def _ensure_timelines_layout(project: Path) -> None:
    """Convert a single-timeline project into the Timelines/ layout (as 'Timeline 01')."""
    if (project / "Timelines" / "project.json").exists():
        return
    content = _read(_content_file(project))
    _rewrite_media_paths(content, project)
    content.setdefault("id", _new_id())
    _write_timeline(project, content, project)
    _write_root(project, content)
    now = _now_us()
    _save_project_json(project, {
        "config": {"color_space": -1, "hdr_vivid": False, "mixed_track_mode_on": False,
                   "render_index_track_mode_on": False, "use_float_render": False},
        "create_time": now, "id": _new_id(), "main_timeline_id": content["id"],
        "timelines": [_timeline_entry("Timeline 01", content["id"])], "version": 0,
    })


def wait_for_draft(folder: Path, timeout_s: float = 30) -> Path:
    folder = Path(folder)
    deadline = time.time() + timeout_s
    last_size = -1
    while time.time() < deadline:
        f = folder / "draft_info.json"
        if f.exists():
            size = f.stat().st_size
            if size > 0 and size == last_size:
                return folder
            last_size = size
        time.sleep(0.25)
    raise DraftSaveFailed(f"draft never appeared at {folder} (VectCutAPI may report success anyway)")


MEDIA_KIND = {".mp4": "video", ".mov": "video", ".m4v": "video", ".webm": "video", ".mkv": "video", ".avi": "video",
              ".mp3": "music", ".wav": "music", ".m4a": "music", ".aac": "music", ".flac": "music", ".ogg": "music",
              ".png": "photo", ".jpg": "photo", ".jpeg": "photo", ".webp": "photo", ".gif": "photo"}


def _media_info(path: str) -> dict:
    """Duration (µs) and upright size, as CapCut lists an imported file in its media panel."""
    kind = MEDIA_KIND.get(Path(path).suffix.lower(), "video")
    if kind == "photo":
        try:
            r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                                "-of", "json", path], capture_output=True, text=True, timeout=30)
            s = (json.loads(r.stdout or "{}").get("streams") or [{}])[0]
        except (OSError, ValueError, subprocess.SubprocessError):
            s = {}
        return {"metetype": "photo", "duration": 5_000_000, "width": s.get("width", 0), "height": s.get("height", 0)}
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
                           capture_output=True, text=True, timeout=30)
        dur = round(float(json.loads(r.stdout or "{}").get("format", {}).get("duration") or 0) * 1_000_000)
    except (OSError, ValueError, subprocess.SubprocessError):
        dur = 0
    w = h = 0
    if kind == "video":
        probed = _probe_video(path)
        if probed:
            w, h, rot = probed
            if abs(rot) % 180 == 90:
                w, h = h, w
    return {"metetype": kind, "duration": dur, "width": w, "height": h}


def import_media(project: Path, files: list) -> dict:
    """Add files to the project's media panel (CapCut's Import list in draft_meta_info.json -> draft_materials
    type 0), under their real names and paths, exactly like importing them in CapCut. Skips files already listed."""
    project = Path(project)
    meta_path = project / "draft_meta_info.json"
    meta = _read(meta_path)
    groups = meta.setdefault("draft_materials", [])
    group = next((g for g in groups if g.get("type") == 0), None)
    if group is None:
        group = {"type": 0, "value": []}
        groups.insert(0, group)
    have = {str(v.get("file_Path", "")).replace("\\", "/").lower() for v in group["value"]}
    added, missing = [], []
    now_s = int(time.time())
    for f in files:
        p = Path(f)
        if not p.exists():
            missing.append(str(f))
            continue
        posix = p.as_posix()
        if posix.lower() in have:
            continue
        info = _media_info(posix)
        group["value"].append({
            "ai_group_type": "", "create_time": now_s, "duration": info["duration"], "enter_from": 0,
            "extra_info": p.name, "file_Path": posix, "height": info["height"], "id": str(uuid.uuid4()),
            "import_time": now_s, "import_time_ms": now_s * 1000, "item_source": 1, "material_color_tag": "",
            "md5": "", "metetype": info["metetype"], "roughcut_time_range": {"duration": info["duration"], "start": 0},
            "sub_time_range": {"duration": -1, "start": -1}, "type": 0, "width": info["width"]})
        have.add(posix.lower())
        added.append(posix)
    if added:
        _write(meta_path, meta)
    return {"added": added, "missing": missing, "total": len(group["value"])}


def link_originals(project: Path, search_dirs=()) -> dict:
    """Make every timeline use the imported original files instead of VectCutAPI's hashed copies in assets/
    (the way CapCut itself links imported media), list those originals in the media panel, and delete copies
    nothing references any more. A clip whose original can't be found keeps its copy."""
    project = Path(project)
    if (project / "Timelines" / "project.json").exists():
        _check_not_busy(project)
    index = _source_index(project, search_dirs)
    content_files = [f for f in project.rglob("draft_*.json")
                     if f.name in CONTENT_FILES and BACKUP_DIR not in f.parts]
    originals, relinked = [], 0
    for f in content_files:
        data = _read(f)
        changed = False
        for kind in ("videos", "audios"):
            for m in data.get("materials", {}).get(kind, []) or []:
                path = str(m.get("path") or "")
                if "/assets/" not in path.replace("\\", "/") and "draftpath_placeholder" not in path:
                    continue
                src = _original_source(m, index)
                if not src or src == path or not Path(src).exists():
                    continue
                src = Path(src).as_posix()
                m.setdefault("remote_url", src)
                m["path"] = src
                m["material_name"] = Path(src).name
                relinked += 1
                changed = True
                originals.append(src)
            for m in data.get("materials", {}).get(kind, []) or []:
                p = str(m.get("path") or "")
                if p and "/assets/" not in p.replace("\\", "/") and Path(p).exists():
                    originals.append(Path(p).as_posix())
        if changed:
            _write(f, data)
    imported = import_media(project, sorted(set(originals)))
    # delete hashed copies that no content file (backups included) still points at
    still_used = set()
    for f in project.rglob("draft_*.json"):
        if f.name in CONTENT_FILES:
            text = f.read_text(encoding="utf-8", errors="ignore").replace("\\\\", "/").replace("\\", "/")
            still_used.update(re.findall(r"assets/[^\"]+", text))
    removed = 0
    for asset in list((project / "assets").rglob("*")) if (project / "assets").exists() else []:
        if asset.is_file() and asset.relative_to(project).as_posix() not in still_used:
            asset.unlink()
            removed += 1
    if (project / "Timelines" / "project.json").exists():
        _mark_own_write(project)
    return {"relinked": relinked, "imported": imported["added"], "copies_removed": removed}


def compose(target: Path, timelines: list[tuple[str, Path]], link_originals: bool = False) -> dict:
    link = link_originals
    target = Path(target)
    _validate_name(target.name)
    if target.exists():
        raise FileExistsError(f"{target} already exists; pick another name or use add-timeline")
    if not timelines:
        raise ValueError("need at least one timeline")
    names = [n for n, _ in timelines]
    for n in names:
        _validate_name(n)
    if len(set(names)) != len(names):
        raise ValueError(f"timeline names must be unique: {names}")
    for _, d in timelines:
        _content_file(Path(d))  # every draft must exist before we create anything

    # Build next to the target, then rename into place, so a failure never leaves a half project.
    work = target.parent / f".{target.name}.building-{uuid.uuid4().hex[:8]}"
    try:
        first = Path(timelines[0][1])
        shutil.copytree(first, work, ignore=shutil.ignore_patterns("assets"))
        (work / "assets").mkdir()

        entries = []
        contents = []
        report = {"rotation_fixed": [], "rotation_unchecked": []}
        for name, draft in timelines:
            content, rep = _import_draft(work, Path(draft), final=target)
            for key in report:
                report[key] += rep[key]
            _write_timeline(work, content, Path(draft))
            contents.append(content)
            entries.append(_timeline_entry(name, content["id"]))

        _write_root(work, contents[0])
        now = _now_us()
        _write(work / "Timelines" / "project.json", {
            "config": {"color_space": -1, "hdr_vivid": False, "mixed_track_mode_on": False,
                       "render_index_track_mode_on": False, "use_float_render": False},
            "create_time": now, "id": _new_id(), "main_timeline_id": contents[0]["id"],
            "timelines": entries, "update_time": now, "version": 0,
        })
        meta_path = work / "draft_meta_info.json"
        if meta_path.exists():
            meta = _read(meta_path)
            meta.update(draft_name=target.name, draft_fold_path=target.as_posix(),
                        draft_root_path=target.parent.as_posix(), draft_id=_new_id(),
                        tm_draft_create=now, tm_draft_modified=now)
            _write(meta_path, meta)
        work.rename(target)
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    _mark_own_write(target)
    if link:
        report["media"] = globals()["link_originals"](target)
    saved = [_save_last(target, n) for n in names]
    return {"project": str(target), "last_snapshot": all(saved), "timelines": [{"name": e["name"], "id": e["id"]} for e in entries], **report}


def add_timeline(project: Path, name: str, draft: Path) -> dict:
    project = Path(project)
    _check_not_busy(project)
    _ensure_timelines_layout(project)
    _ensure_new_name(project, name)
    content, report = _import_draft(project, Path(draft))
    _write_timeline(project, content, Path(draft))
    pj = _project_json(project)
    pj["timelines"].append(_timeline_entry(name, content["id"]))
    _save_project_json(project, pj)
    saved = _save_last(project, name)
    return {"name": name, "id": content["id"], "last_snapshot": saved, **report}


def duplicate_timeline(project: Path, source_name: str, new_name: str) -> dict:
    project = Path(project)
    _check_not_busy(project)
    _ensure_timelines_layout(project)
    _ensure_new_name(project, new_name)
    src = project / "Timelines" / _find(project, source_name)["id"]
    new_id = _new_id()
    dst = project / "Timelines" / new_id
    shutil.copytree(src, dst)
    for name in CONTENT_FILES:
        if (dst / name).exists():
            content = _read(dst / name)
            content["id"] = new_id
            _write(dst / name, content)
    pj = _project_json(project)
    pj["timelines"].append(_timeline_entry(new_name, new_id))
    _save_project_json(project, pj)
    return {"name": new_name, "id": new_id}


def replace_timeline(project: Path, name: str, draft: Path) -> dict:
    """Edit a timeline in place: back it up, then swap in a new draft's content, keeping its id."""
    project = Path(project)
    _check_not_busy(project)
    _ensure_timelines_layout(project)
    tl = _find(project, name)
    backup = backup_timeline(project, name)
    content, report = _import_draft(project, Path(draft))
    content["id"] = tl["id"]
    folder = project / "Timelines" / tl["id"]
    for fname in CONTENT_FILES:
        _write(folder / fname, content)
    if tl["main"]:
        _write_root(project, content)
    _save_project_json(project, _project_json(project))
    saved = _save_last(project, name)
    return {"name": name, "id": tl["id"], "backup": str(backup), "last_snapshot": saved, **report}


def add_tracks(project: Path, name: str, draft: Path, track_type: str = "audio") -> dict:
    """Merge one draft's tracks of `track_type` (e.g. music) into an existing timeline, keeping
    everything already there (the user's captions and hand edits). Backs the timeline up first."""
    project = Path(project)
    _check_not_busy(project)
    _ensure_timelines_layout(project)
    tl = _find(project, name)
    backup = backup_timeline(project, name)
    folder = project / "Timelines" / tl["id"]
    timeline_file = _content_file(folder)
    timeline = _read(timeline_file)
    incoming, report = _import_draft(project, Path(draft))

    new_tracks = [t for t in incoming.get("tracks", []) if t.get("type") == track_type and t.get("segments")]
    if not new_tracks:
        raise ValueError(f"draft {draft} has no {track_type} tracks with segments")
    wanted = set()
    for t in new_tracks:
        for s in t["segments"]:
            wanted.add(s.get("material_id"))
            wanted.update(s.get("extra_material_refs") or [])
    # Once CapCut has saved the project its own media paths are placeholders; use the same form so the
    # project still opens if it's moved or renamed.
    placeholder = _placeholder(project, timeline_file)
    local = project.as_posix() + "/assets/"
    mats = timeline.setdefault("materials", {})
    for key, items in incoming.get("materials", {}).items():
        if isinstance(items, list):
            have = {m.get("id") for m in mats.get(key, []) if isinstance(m, dict)}
            add = [m for m in items if isinstance(m, dict) and m.get("id") in wanted and m.get("id") not in have]
            for m in add:
                if placeholder and isinstance(m.get("path"), str) and m["path"].startswith(local):
                    m["path"] = placeholder + "/assets/" + m["path"][len(local):]
            if add:
                mats.setdefault(key, []).extend(add)
    timeline.setdefault("tracks", []).extend(new_tracks)
    end = max(s["target_timerange"]["start"] + s["target_timerange"]["duration"]
              for t in new_tracks for s in t["segments"])
    timeline["duration"] = max(timeline.get("duration", 0), end)

    for fname in CONTENT_FILES:
        _write(folder / fname, timeline)
    if tl["main"]:
        _write_root(project, timeline)
    _save_project_json(project, _project_json(project))
    saved = _save_last(project, name)
    return {"name": name, "id": tl["id"], "backup": str(backup), "last_snapshot": saved, "tracks_added": len(new_tracks), **report}


def _span(seg: dict) -> tuple[int, int]:
    tr = seg["target_timerange"]
    return tr["start"], tr["start"] + tr["duration"]


def _materials_by_id(content: dict) -> dict:
    return {m["id"]: (key, m) for key, items in content.get("materials", {}).items() if isinstance(items, list)
            for m in items if isinstance(m, dict) and "id" in m}


def add_overlay(project: Path, name: str, draft: Path, track_name: str = "video_overlay") -> dict:
    """Add every video segment of a VectCutAPI draft (e.g. one B-roll clip) onto an existing video track
    of a timeline, keeping everything already there (captions, hand edits) byte-for-byte. Each new segment
    takes the shape of a segment already on that track, with its companion materials cloned under new ids.
    Refuses overlaps with the track's clips. Backs the timeline up first."""
    project = Path(project)
    _check_not_busy(project)
    _ensure_timelines_layout(project)
    tl = _find(project, name)
    folder = project / "Timelines" / tl["id"]
    timeline_file = _content_file(folder)
    timeline = _read_exact(timeline_file)

    tracks = timeline.get("tracks", [])
    matches = [i for i, t in enumerate(tracks) if t.get("type") == "video" and t.get("name") == track_name]
    if len(matches) != 1:
        names = [t.get("name") for t in tracks if t.get("type") == "video"]
        raise ValueError(f"{name!r} needs exactly one video track named {track_name!r} (found {len(matches)}); "
                         f"its video tracks are {names}")
    track_index = matches[0]
    target = tracks[track_index]

    # Check the incoming clips fit before touching anything.
    plain = _read(_content_file(Path(draft)))
    incoming_segs = sorted((s for t in plain.get("tracks", []) if t.get("type") == "video"
                            for s in t.get("segments", [])), key=lambda s: s["target_timerange"]["start"])
    if not incoming_segs:
        raise ValueError(f"draft {draft} has no video segments")
    taken = sorted([(*_span(s), f"existing clip at {_span(s)[0] / 1e6:.3f}s") for s in target.get("segments", [])]
                   + [(*_span(s), f"new clip at {_span(s)[0] / 1e6:.3f}s") for s in incoming_segs])
    for (a0, a1, a), (b0, b1, b) in zip(taken, taken[1:]):
        if b0 < a1:
            raise ValueError(f"overlap on track {track_name!r}: {a} ({a0 / 1e6:.3f}-{a1 / 1e6:.3f}s) and {b} "
                             f"({b0 / 1e6:.3f}-{b1 / 1e6:.3f}s); nothing was changed")

    templates = target.get("segments") or [s for t in tracks if t.get("type") == "video" for s in t.get("segments", [])]
    if not templates:
        raise ValueError(f"{name!r} has no video segment to copy the segment shape from")
    template = max(templates, key=lambda s: s["target_timerange"]["start"])

    backup = backup_timeline(project, name)
    if tl["main"]:
        for fname in CONTENT_FILES:
            if (project / fname).exists():
                shutil.copy2(project / fname, backup / f"root_{fname}")
    incoming, report = _import_draft(project, Path(draft))
    in_mats = _materials_by_id(incoming)
    tl_mats = _materials_by_id(timeline)
    mats = timeline.setdefault("materials", {})
    placeholder = _placeholder(project, timeline_file)
    local = project.as_posix() + "/assets/"

    def add_material(kind: str, m: dict) -> str:
        m = copy.deepcopy(m)
        m["id"] = _new_id()
        if placeholder and isinstance(m.get("path"), str) and m["path"].startswith(local):
            m["path"] = placeholder + "/assets/" + m["path"][len(local):]
        mats.setdefault(kind, []).append(m)
        return m["id"]

    added = []
    in_by_id = {s["id"]: s for t in incoming.get("tracks", []) if t.get("type") == "video" for s in t.get("segments", [])}
    for s0 in incoming_segs:
        src = in_by_id[s0["id"]]
        seg = copy.deepcopy(template)
        for key in ("source_timerange", "target_timerange", "speed", "volume", "clip", "reverse", "is_loop"):
            if key in src:
                seg[key] = copy.deepcopy(src[key])
        if src.get("volume"):
            seg["last_nonzero_volume"] = src["volume"]
        seg.update(id=_new_id(), keyframe_refs=[], common_keyframes=[], group_id="", raw_segment_id="",
                   track_render_index=template.get("track_render_index", track_index))
        kind, video = in_mats[src["material_id"]]
        seg["material_id"] = add_material(kind, video)
        refs, covered = [], set()
        for r in template.get("extra_material_refs") or []:
            k, m = tl_mats.get(r, (None, None))
            if k in COMPANION_KINDS:
                m = copy.deepcopy(m)
                if k == "speeds":
                    m["speed"] = seg.get("speed", 1.0)
                refs.append(add_material(k, m))
                covered.add(k)
        for r in src.get("extra_material_refs") or []:  # masks, transitions, ... set in the draft
            k, m = in_mats.get(r, (None, None))
            if k and k not in covered:
                refs.append(add_material(k, m))
        seg["extra_material_refs"] = refs
        segs = target.setdefault("segments", [])
        at = next((i for i, s in enumerate(segs) if _span(s)[0] > _span(seg)[0]), len(segs))
        segs.insert(at, seg)
        added.append({"id": seg["id"], "at": _span(seg)[0] / 1e6, "duration": seg["target_timerange"]["duration"] / 1e6,
                      "source": video.get("remote_url") or video.get("path")})

    old_duration = timeline.get("duration", 0)
    timeline["duration"] = max(old_duration, max(_span(s)[1] for s in target["segments"]))

    _write_newest_content(folder, timeline)
    if tl["main"]:
        _write_newest_content(project, timeline)
    _save_project_json(project, _project_json(project))
    saved = _save_last(project, name)
    return {"name": name, "id": tl["id"], "track": track_name, "backup": str(backup), "last_snapshot": saved,
            "segments_added": added,
            "duration": timeline["duration"] / 1e6, "duration_changed": timeline["duration"] != old_duration,
            **report}


def _probe_media(path: str) -> dict:
    """{duration_us, width, height, kind} of a media file ('photo' for stills, 'video', 'audio')."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"media file not found: {path}")
    if p.suffix.lower() in PHOTO_EXTS:
        info = _probe_video(path) or (0, 0, 0)
        return {"duration_us": PHOTO_DURATION_US, "width": info[0], "height": info[1], "kind": "photo"}
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
                          "-of", "json", path], capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
    data = json.loads(out.stdout or "{}")
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    dur = int(round(float(data.get("format", {}).get("duration", 0)) * 1_000_000))
    if video:
        return {"duration_us": dur, "width": int(video.get("width", 0)), "height": int(video.get("height", 0)), "kind": "video"}
    return {"duration_us": dur, "width": 0, "height": 0, "kind": "audio"}


def _point_material_at(m: dict, path: str, info: dict) -> None:
    """Make a (cloned) video/audio material describe another file."""
    name = Path(path).name
    m["path"] = Path(path).as_posix()
    m["duration"] = info["duration_us"]
    if "material_name" in m:
        m["material_name"] = name
    if "name" in m:
        m["name"] = name
    if info["kind"] in ("video", "photo"):
        m["type"] = info["kind"]
        m["width"], m["height"] = info["width"], info["height"]
    for key in ("remote_url", "media_path"):
        if key in m:
            m[key] = ""


def _new_material_ids(m: dict) -> str:
    new = _new_id().replace("-", "").lower()
    m["id"] = new
    for key in ("material_id", "local_material_id", "music_id"):
        if key in m:
            m[key] = new
    if "unique_id" in m:
        m["unique_id"] = uuid.uuid4().hex
    return new


class _Patcher:
    """Applies patch ops to one timeline's content (already loaded with _read_exact)."""

    def __init__(self, content: dict):
        self.c = content
        self.mats = content.setdefault("materials", {})
        self.names = {}  # "@name" -> segment id, for segments created by split/insert

    # --- lookups -------------------------------------------------------------------------
    def _by_id(self) -> dict:
        return {m["id"]: (k, m) for k, items in self.mats.items() if isinstance(items, list)
                for m in items if isinstance(m, dict) and "id" in m}

    def _resolve(self, sid: str) -> str:
        return self.names.get(sid.lstrip("@"), sid) if isinstance(sid, str) and sid.startswith("@") else sid

    def _locate(self, sid: str) -> tuple[dict, dict]:
        sid = self._resolve(sid)
        for t in self.c.get("tracks", []):
            for s in t.get("segments", []):
                if s.get("id") == sid:
                    return t, s
        raise KeyError(f"no segment with id {sid!r} on this timeline")

    def _track(self, name: str, like_type: str | None = None, before: str | None = None) -> dict:
        found = [t for t in self.c.get("tracks", []) if t.get("name") == name]
        if len(found) > 1:
            raise ValueError(f"more than one track named {name!r}")
        if found:
            return found[0]
        if not like_type:
            raise KeyError(f"no track named {name!r}")
        src = next((t for t in self.c["tracks"] if t.get("type") == like_type), None)
        if src is None:
            raise KeyError(f"no track named {name!r} and no {like_type} track to copy its shape from")
        new = {k: copy.deepcopy(v) for k, v in src.items() if k != "segments"}
        new.update(id=_new_id(), name=name, segments=[])
        at = next((i for i, t in enumerate(self.c["tracks"]) if before and t.get("name") == before), None)
        if at is None:
            self.c["tracks"].append(new)
        else:  # keep the stacking order: the new track goes just under `before`
            self.c["tracks"].insert(at, new)
        return new

    # --- material helpers ------------------------------------------------------------------
    def _clone_material(self, mid: str) -> str:
        kind, m = self._by_id()[mid]
        m = copy.deepcopy(m)
        new = _new_material_ids(m) if kind in ("videos", "audios") else _new_id()
        m["id"] = new
        self.mats[kind].append(m)
        return new

    def _clone_segment(self, seg: dict) -> dict:
        new = copy.deepcopy(seg)
        new["id"] = _new_id().replace("-", "").lower()
        new["material_id"] = self._clone_material(seg["material_id"])
        new["extra_material_refs"] = [self._clone_material(r) for r in seg.get("extra_material_refs") or []
                                      if r in self._by_id()]
        new["keyframe_refs"] = []
        new["common_keyframes"] = []
        return new

    def _set_speed(self, seg: dict, speed) -> None:
        seg["speed"] = speed
        by = self._by_id()
        for r in seg.get("extra_material_refs") or []:
            k, m = by.get(r, (None, None))
            if k == "speeds":
                m["speed"] = speed

    def _apply_fields(self, seg: dict, op: dict) -> None:
        tr, sr = seg["target_timerange"], seg.get("source_timerange")
        if "start" in op:
            tr["start"] = int(op["start"])
        if "duration" in op:
            tr["duration"] = int(op["duration"])
        if sr is not None:
            if "src_start" in op:
                sr["start"] = int(op["src_start"])
            if "src_duration" in op:
                sr["duration"] = int(op["src_duration"])
        if "speed" in op:
            self._set_speed(seg, op["speed"])
        clip = seg.get("clip")
        if clip is not None:
            if "scale" in op:
                clip.setdefault("scale", {})
                clip["scale"]["x"] = clip["scale"]["y"] = op["scale"]
            if "x" in op:
                clip.setdefault("transform", {})["x"] = op["x"]
            if "y" in op:
                clip.setdefault("transform", {})["y"] = op["y"]
        if "flip" in op and clip is not None:
            clip.setdefault("flip", {"horizontal": False, "vertical": False})["horizontal"] = bool(op["flip"])
        if "volume" in op:
            seg["volume"] = op["volume"]
            if op["volume"]:
                seg["last_nonzero_volume"] = op["volume"]
        for key in ("render_index", "track_render_index"):  # stacking order of video tracks
            if key in op:
                seg[key] = int(op[key])

    def _repoint(self, seg: dict, path: str) -> None:
        info = _probe_media(path)
        kind, m = self._by_id()[seg["material_id"]]
        if sum(1 for t in self.c["tracks"] for s in t.get("segments", []) if s.get("material_id") == m["id"]) > 1:
            seg["material_id"] = self._clone_material(m["id"])
            kind, m = self._by_id()[seg["material_id"]]
        _point_material_at(m, path, info)

    # --- ops -----------------------------------------------------------------------------
    def set(self, op: dict) -> dict:
        _, seg = self._locate(op["id"])
        if op.get("file"):
            self._repoint(seg, op["file"])
        self._apply_fields(seg, op)
        return {"op": "set", "id": seg["id"]}

    def remove(self, op: dict) -> dict:
        t, seg = self._locate(op["id"])
        t["segments"].remove(seg)
        used = {s.get("material_id") for tr in self.c["tracks"] for s in tr.get("segments", [])}
        used |= {r for tr in self.c["tracks"] for s in tr.get("segments", []) for r in s.get("extra_material_refs") or []}
        drop = {seg.get("material_id"), *(seg.get("extra_material_refs") or [])} - used
        for kind, items in self.mats.items():
            if isinstance(items, list):
                self.mats[kind] = [m for m in items if not (isinstance(m, dict) and m.get("id") in drop)]
        return {"op": "remove", "id": seg["id"]}

    def insert(self, op: dict) -> dict:
        info = _probe_media(op["file"])
        like_type = "audio" if info["kind"] == "audio" else "video"
        track = self._track(op["track"], like_type, op.get("track_before"))
        if op.get("like"):
            _, template = self._locate(op["like"])
        else:
            pool = track.get("segments") or [s for t in self.c["tracks"] if t.get("type") == like_type
                                             for s in t.get("segments", [])]
            if not pool:
                raise ValueError(f"no {like_type} segment to copy a segment shape from")
            template = max(pool, key=lambda s: s["target_timerange"]["start"])
        seg = self._clone_segment(template)
        _point_material_at(self._by_id()[seg["material_id"]][1], op["file"], info)
        seg.setdefault("source_timerange", {"start": 0, "duration": 0})
        self._apply_fields(seg, {"speed": 1.0, **op})
        if "src_duration" not in op:
            seg["source_timerange"]["duration"] = int(round(seg["target_timerange"]["duration"] * seg.get("speed", 1.0)))
        track["segments"].append(seg)
        track["segments"].sort(key=lambda s: s["target_timerange"]["start"])
        if op.get("name"):
            self.names[op["name"].lstrip("@")] = seg["id"]
        return {"op": "insert", "id": seg["id"], "track": op["track"]}

    def split(self, op: dict) -> dict:
        t, seg = self._locate(op["id"])
        at = int(op["at"])
        s0, s1 = _span(seg)
        if not s0 < at < s1:
            raise ValueError(f"split point {at} is outside segment {seg['id']} ({s0}-{s1})")
        right = self._clone_segment(seg)
        left_dur = at - s0
        speed = float(seg.get("speed", 1.0))
        seg["target_timerange"]["duration"] = left_dur
        right["target_timerange"] = {"start": at, "duration": s1 - at}
        if seg.get("source_timerange"):
            src0, srcd = seg["source_timerange"]["start"], seg["source_timerange"]["duration"]
            left_src = int(round(left_dur * speed))
            seg["source_timerange"]["duration"] = left_src
            right["source_timerange"] = {"start": src0 + left_src, "duration": srcd - left_src}
        t["segments"].insert(t["segments"].index(seg) + 1, right)
        if op.get("name"):
            self.names[op["name"].lstrip("@")] = right["id"]
        return {"op": "split", "id": seg["id"], "new_id": right["id"]}

    def ripple(self, op: dict) -> dict:
        at, delta = int(op["at"]), int(op["delta"])
        moved = 0
        for t in self.c.get("tracks", []):
            for s in t.get("segments", []):
                if s["target_timerange"]["start"] >= at and s.get("id") not in set(map(self._resolve, op.get("except", []))):
                    s["target_timerange"]["start"] += delta
                    moved += 1
        return {"op": "ripple", "at": at, "delta": delta, "moved": moved}

    def transition(self, op: dict) -> dict:
        """Put a CapCut transition on the cut after segment `id` (CapCut stores it on the outgoing
        segment). The transition material is copied by name from another draft that used it, so its
        effect files are already in CapCut's cache; segment times never move (CapCut overlaps them)."""
        t, seg = self._locate(op["id"])
        segs = sorted(t["segments"], key=lambda s: s["target_timerange"]["start"])
        i = segs.index(seg)
        if i + 1 >= len(segs) or segs[i + 1]["target_timerange"]["start"] != _span(seg)[1]:
            raise ValueError(f"segment {seg['id']} has no clip right after it to transition into")
        src = Path(op["from_draft"])
        src = _content_file(src) if src.is_dir() else src
        found = [m for m in _read(src).get("materials", {}).get("transitions", []) if m.get("name") == op["name"]]
        if not found:
            raise KeyError(f"no transition named {op['name']!r} in {src}")
        m = copy.deepcopy(found[0])
        if m.get("path") and not Path(m["path"]).exists():
            raise FileNotFoundError(f"{op['name']!r} effect files are not in CapCut's cache ({m['path']})")
        m["id"] = _new_id()
        if "duration" in op:
            m["duration"] = int(op["duration"])
        by = self._by_id()
        refs = [r for r in seg.get("extra_material_refs") or [] if by.get(r, (None,))[0] != "transitions"]
        dropped = set(seg.get("extra_material_refs") or []) - set(refs)
        self.mats["transitions"] = [x for x in self.mats.get("transitions", []) if x.get("id") not in dropped]
        self.mats["transitions"].append(m)
        # CapCut's order: speeds, placeholder_infos, hsl, transitions, canvases, ...
        after = [k for k, r in enumerate(refs) if by.get(r, (None,))[0] in ("speeds", "placeholder_infos", "hsl")]
        refs.insert(after[-1] + 1 if after else 0, m["id"])
        seg["extra_material_refs"] = refs
        return {"op": "transition", "id": seg["id"], "name": m["name"], "duration": m["duration"]}

    def _grade_template(self, kind: str, value: float) -> dict:
        return {"id": _new_id(), "effect_id": "7501974767453474064", "resource_id": "7501974767453474064",
                "third_resource_id": "", "name": "", "report_name": "", "type": kind, "sub_type": "none",
                "path": GRADE_CACHE, "value": value, "visible": True, "item_effect_type": 0, "category_id": "",
                "category_name": "", "category_key": "", "sub_category_id": "", "sub_category_name": "",
                "platform": "all", "apply_target_type": 0, "source_platform": 1, "version": GRADE_VERSIONS[kind],
                "adjust_params": [], "time_range": None, "formula_id": "", "enable_skin_tone_correction": False,
                "algorithm_artifact_path": "", "intensity_key": "", "face_adjust_params": [], "exclusion_group": [],
                "panel_id": "", "bloom_params": None, "request_id": "",
                "color_match_info": {"target_feature_path": "", "source_feature_path": "", "target_image_path": ""},
                "multi_language_current": "", "lumi_hub_path": GRADE_CACHE + "/lumi_hub_path",
                "covering_relation_change": 0, "beauty_face_auto_preset_id": "", "beauty_body_auto_preset_id": "",
                "beauty_face_auto_retouch_info": {"face_id": [], "beauty_face_auto_retouch_id": ""},
                "smart_color_mode": 0, "is_from_intelligent_quality": False}

    def grade(self, op: dict) -> dict:
        """Colour-grade segments with Adjustment sliders (-100..100): temperature, saturation, brightness,
        contrast. Each becomes a materials.effects entry referenced from the segment's extra_material_refs
        (after speeds/placeholder_infos, CapCut's spot); a slider already on the segment is replaced, one
        not named is left alone, so re-running is safe. Segments: "ids": [...] / "id", or "track" (name,
        default the first video track) with "index" or "range": [first, last] (0-based, inclusive)."""
        sliders = {k: op[k] for k in GRADE_VERSIONS if k in op}
        if not sliders:
            raise ValueError(f"grade needs at least one of {', '.join(GRADE_VERSIONS)}")
        for k, v in sliders.items():
            if not isinstance(v, (int, float)) or isinstance(v, bool) or not -100 <= v <= 100:
                raise ValueError(f"grade {k} must be a number from -100 to 100, got {v!r}")
        if op.get("ids") or op.get("id"):
            segs = [self._locate(i)[1] for i in (op.get("ids") or [op["id"]])]
        else:
            track = self._track(op["track"]) if op.get("track") else next(
                (t for t in self.c.get("tracks", []) if t.get("type") == "video"), None)
            if track is None:
                raise KeyError("no video track to grade")
            ordered = sorted(track["segments"], key=lambda s: s["target_timerange"]["start"])
            if "index" in op:
                lo = hi = int(op["index"])
            elif "range" in op:
                lo, hi = int(op["range"][0]), int(op["range"][1])
            else:
                raise ValueError("grade needs ids, or a track with index / range")
            if not 0 <= lo <= hi < len(ordered):
                raise ValueError(f"grade segment range {lo}-{hi} is outside track {track.get('name')!r} "
                                 f"(0-{len(ordered) - 1})")
            segs = ordered[lo:hi + 1]
        for seg in segs:
            by = self._by_id()
            refs = list(seg.get("extra_material_refs") or [])
            old = {r for r in refs if by.get(r, (None, {}))[0] == "effects" and by[r][1].get("type") in sliders}
            refs = [r for r in refs if r not in old]
            others = {r for t in self.c.get("tracks", []) for s in t.get("segments", []) if s is not seg
                      for r in s.get("extra_material_refs") or []}
            gone = old - others
            self.mats["effects"] = [m for m in self.mats.get("effects", []) if m.get("id") not in gone]
            # keep CapCut's slider order among the grade entries already on the segment
            existing = [r for r in refs if by.get(r, (None, {}))[0] == "effects" and by[r][1].get("type") in GRADE_ORDER]
            new = {k: self._grade_template(k, v / 100) for k, v in sliders.items()}
            self.mats.setdefault("effects", []).extend(new.values())
            entries = [(by[r][1]["type"], r) for r in existing] + [(k, m["id"]) for k, m in new.items()]
            entries.sort(key=lambda e: GRADE_ORDER.index(e[0]))
            refs = [r for r in refs if r not in existing]
            after = [k for k, r in enumerate(refs) if by.get(r, (None,))[0] in ("speeds", "placeholder_infos")]
            at = after[-1] + 1 if after else 0
            refs[at:at] = [r for _, r in entries]
            seg["extra_material_refs"] = refs
        return {"op": "grade", "segments": [s["id"] for s in segs], "set": sliders}

    # --- checks --------------------------------------------------------------------------
    def validate(self) -> None:
        for t in self.c.get("tracks", []):
            spans = sorted((_span(s) + (s.get("id"),)) for s in t.get("segments", []))
            for (a0, a1, a), (b0, b1, b) in zip(spans, spans[1:]):
                if b0 < a1:
                    raise ValueError(f"overlap on track {t.get('name')!r}: {a} ({a0}-{a1}) and {b} ({b0}-{b1})")
            for s in t.get("segments", []):
                if s["target_timerange"]["duration"] <= 0 or s["target_timerange"]["start"] < 0:
                    raise ValueError(f"segment {s.get('id')} has a bad time range {s['target_timerange']}")
        ends = [_span(s)[1] for t in self.c.get("tracks", []) for s in t.get("segments", [])]
        self.c["duration"] = max(ends, default=0)


def patch_timeline(project: Path, name: str, ops, dry_run: bool = False) -> dict:
    """Edit a timeline in place op by op, keeping everything else (the user's hand edits, keyframes,
    captions) byte-for-byte. Ops (times in microseconds, segments by their CapCut id or an "@name"
    given to a segment made earlier in the same patch):
        {"op": "set", "id", [file], [start, duration, src_start, src_duration, speed, scale, x, y, volume]}
        {"op": "remove", "id"}
        {"op": "insert", "track", "file", "start", "duration", [src_start, src_duration, speed, scale, x, y,
         volume, like (segment id to copy the shape from), name, render_index, track_render_index,
         track_before (a missing track is created just before this track name)]}
        {"op": "split", "id", "at", [name (for the right half)]}
        {"op": "ripple", "at", "delta", [except: ids]}   shift every segment starting at/after `at`
        {"op": "transition", "id", "name", "from_draft", [duration]}   CapCut transition on the cut after
         segment `id`, copied by name from another draft (its effect must be in CapCut's cache)
        {"op": "grade", ("ids": [..] | "track", "index" | "range": [first, last]), [temperature, saturation,
         brightness, contrast: -100..100]}   colour-grade segments with Adjustment sliders (idempotent)
    All ops are applied in memory and the result is checked (no overlaps) before anything is written.
    Writes the timeline's draft_content.json (newest) + draft_info.json, and the root files for the main
    timeline. Backs the timeline up first."""
    project = Path(project)
    if not dry_run:
        _check_not_busy(project)
    _ensure_timelines_layout(project)
    if isinstance(ops, (str, Path)):
        ops = _read(Path(ops))
    if isinstance(ops, dict):
        ops = ops["ops"]
    tl = _find(project, name)
    folder = project / "Timelines" / tl["id"]
    content = _read_exact(_content_file(folder))
    before = content.get("duration", 0)
    p = _Patcher(content)
    done = []
    for i, op in enumerate(ops):
        fn = getattr(p, op.get("op", ""), None)
        if op.get("op") not in ("set", "remove", "insert", "split", "ripple", "transition", "grade") or fn is None:
            raise ValueError(f"op {i}: unknown op {op.get('op')!r}")
        try:
            done.append({"n": i, **fn(op)})
        except (KeyError, ValueError, FileNotFoundError) as e:
            raise ValueError(f"op {i} ({op.get('op')}): {e}; nothing was written") from e
    p.validate()
    result = {"name": name, "id": tl["id"], "ops_applied": len(done), "duration_before": before / 1e6,
              "duration": content["duration"] / 1e6, "dry_run": dry_run, "results": done}
    if dry_run:
        return result
    backup = backup_timeline(project, name)
    if tl["main"]:
        for fname in CONTENT_FILES:
            if (project / fname).exists():
                shutil.copy2(project / fname, backup / f"root_{fname}")
    _write_newest_content(folder, content)
    if tl["main"]:
        _write_newest_content(project, content)
    _save_project_json(project, _project_json(project))
    saved = _save_last(project, name)
    return {**result, "backup": str(backup), "last_snapshot": saved}


def _vectcut_hash(url: str) -> str:
    """VectCutAPI names copied media <kind>_<this>.<ext> (util.url_to_hash)."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _source_index(project: Path, search_dirs=()) -> dict:
    """Original file for each material, from every content file in the project (other timelines,
    the root and backups keep remote_url after CapCut drops it), keyed by material id and asset file
    name, plus 'hash:<vectcut hash>' for every file under search_dirs."""
    index = {}
    for f in project.rglob("draft_*.json"):
        if f.name not in CONTENT_FILES:
            continue
        try:
            mats = _read(f).get("materials", {})
        except (OSError, ValueError):
            continue
        for items in mats.values():
            for m in items if isinstance(items, list) else []:
                if isinstance(m, dict) and m.get("remote_url"):
                    index.setdefault(m.get("id"), m["remote_url"])
                    for key in (m.get("material_name"), Path(str(m.get("path", ""))).name):
                        if key:
                            index.setdefault(key, m["remote_url"])
    for d in search_dirs:
        for file in Path(d).rglob("*"):
            if file.is_file():
                for variant in (str(file), file.as_posix()):
                    index.setdefault("hash:" + _vectcut_hash(variant), variant)
    return index


def _original_source(m: dict, index: dict) -> str | None:
    if m.get("remote_url"):
        return m["remote_url"]
    path = m.get("path") or ""
    name = Path(path).name
    hashed = re.match(r"(?:video|audio|image)_([0-9a-f]{16})\.", name)
    if path and not hashed and "placeholder" not in path and Path(path).is_file():
        return path  # a live original (e.g. repointed by patch) beats stale backups indexed by material id
    return (index.get(m.get("id")) or index.get(name)
            or (index.get("hash:" + hashed.group(1)) if hashed else None) or path or None)


def _text_of(m: dict) -> str | None:
    """CapCut stores text as a JSON string {"text": ..., "styles": [...]}."""
    content = m.get("content")
    if not isinstance(content, str):
        return None
    try:
        return json.loads(content).get("text", content)
    except (ValueError, AttributeError):
        return content


def segments(project: Path, name: str, search_dirs=()) -> dict:
    """What is on a timeline: timeline duration, and per segment its timing, layout
    (transform/scale/rotation/crop/mask), stored size, text and ORIGINAL file — for QA and for spotting the
    user's hand edits before a revision. CapCut-saved paths (##_draftpath_placeholder_…##/assets/...)
    are mapped back to the source by material id / asset name from the project's other content
    files, or by VectCutAPI's hash naming against files under search_dirs."""
    project = Path(project)
    tl = _find(project, name)
    folder = project / "Timelines" / tl["id"] if (project / "Timelines" / "project.json").exists() else project
    c = _read(_content_file(folder))
    index = _source_index(project, search_dirs)
    by_id = {m["id"]: (key, m) for key, items in c.get("materials", {}).items() if isinstance(items, list)
             for m in items if isinstance(m, dict) and "id" in m}
    out = []
    for t in c.get("tracks", []):
        for s in t.get("segments", []):
            kind, m = by_id.get(s.get("material_id"), ("?", {}))
            tr, sr = s.get("target_timerange") or {}, s.get("source_timerange") or {}
            clip = s.get("clip") or {}
            crop = m.get("crop")
            masks = [by_id[r][1] for r in s.get("extra_material_refs") or []
                     if r in by_id and by_id[r][0] in ("common_mask", "masks")]
            out.append({
                "id": s.get("id"), "track": t.get("name") or t.get("type"), "track_type": t.get("type"), "material_type": kind,
                "source": _original_source(m, index) if m.get("path") or m.get("remote_url") else None,
                "path": m.get("path"), "remote_url": m.get("remote_url"),
                "size": f"{m['width']}x{m['height']}" if m.get("width") and m.get("height") else None,
                "text": _text_of(m) if kind == "texts" else None,
                "at": tr.get("start", 0) / 1e6, "duration": tr.get("duration", 0) / 1e6,
                "src_in": sr.get("start", 0) / 1e6 if sr else None, "speed": s.get("speed"),
                "volume": s.get("volume"),
                "transform": clip.get("transform"), "scale": clip.get("scale"), "rotation": clip.get("rotation"),
                "crop": crop if crop and crop != FULL_FRAME_CROP else None,
                "mask": [{"name": mm.get("name"), "config": mm.get("config")} for mm in masks],
            })
    return {"timeline": name, "duration": c.get("duration", 0) / 1e6, "segments": out}


def last_path(project: Path, name: str) -> Path:
    """Where the snapshot of the timeline as we last wrote it lives (edit_diff diff --last reads it)."""
    return Path(project) / BACKUP_DIR / f"{name}.last.json"


def _save_last(project: Path, name: str) -> bool:
    """Snapshot the timeline right after one of our writes, so the learning step can tell the editor's
    hand edits from our own patches. Never breaks the write it follows. On failure the old snapshot is
    removed (a stale one would hide our own patches as hand edits) and False is returned."""
    out = last_path(project, name)
    tmp = out.with_name(out.name + ".tmp")
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(segments(project, name), ensure_ascii=False), encoding="utf-8")
        tmp.replace(out)  # atomic: a truncated snapshot is never read
        return True
    except Exception as e:  # the write already succeeded; a missing snapshot only costs the learning diff
        print(f"warning: could not save the last-write snapshot of {name!r}: {e}", file=sys.stderr)
        for f in (tmp, out):
            try:
                f.unlink(missing_ok=True)
            except OSError:
                pass
        return False


def backup_timeline(project: Path, name: str) -> Path:
    project = Path(project)
    _ensure_timelines_layout(project)
    tid = _find(project, name)["id"]
    dst = project / BACKUP_DIR / f"{tid}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
    n = 1
    while dst.exists():  # two writes in the same second
        n += 1
        dst = dst.with_name(f"{dst.name.split('_')[0]}_{n}")
    shutil.copytree(project / "Timelines" / tid, dst)
    (dst / "timeline_name.txt").write_text(name, encoding="utf-8")
    return dst


def list_timelines(project: Path) -> list[dict]:
    project = Path(project)
    if not (project / "Timelines" / "project.json").exists():
        return [{"name": "Timeline 01", "id": _read(_content_file(project)).get("id"), "main": True}]
    pj = _project_json(project)
    return [{"name": t["name"], "id": t["id"], "main": t["id"] == pj["main_timeline_id"]}
            for t in pj["timelines"] if not t.get("is_marked_delete")]


def main(argv: list[str]) -> None:
    if not argv or len(argv) - 1 < MIN_ARGS.get(argv[0], 0):
        raise SystemExit(__doc__)
    cmd, args = argv[0], argv[1:]
    if cmd == "compose":
        keep = "--keep-copies" in args
        args = [a for a in args if a != "--keep-copies"]
        out = compose(Path(args[0]), [tuple(a.split("=", 1)) for a in args[1:]], link_originals=not keep)
    elif cmd == "import":
        out = import_media(Path(args[0]), args[1:])
    elif cmd == "link-originals":
        out = link_originals(Path(args[0]), [Path(d) for d in args[1:]])
    elif cmd == "add-timeline":
        out = add_timeline(Path(args[0]), args[1], Path(args[2]))
    elif cmd == "duplicate":
        out = duplicate_timeline(Path(args[0]), args[1], args[2])
    elif cmd == "replace":
        out = replace_timeline(Path(args[0]), args[1], Path(args[2]))
    elif cmd == "add-tracks":
        out = add_tracks(Path(args[0]), args[1], Path(args[2]), args[3] if len(args) > 3 else "audio")
    elif cmd == "add-overlay":
        out = add_overlay(Path(args[0]), args[1], Path(args[2]), args[3] if len(args) > 3 else "video_overlay")
    elif cmd == "patch":
        dry = "--dry-run" in args
        args = [a for a in args if a != "--dry-run"]
        out = patch_timeline(Path(args[0]), args[1], Path(args[2]), dry_run=dry)
    elif cmd == "segments":
        out = segments(Path(args[0]), args[1], [Path(d) for d in args[2:]])
    elif cmd == "backup":
        out = {"backup": str(backup_timeline(Path(args[0]), args[1]))}
    elif cmd == "list":
        out = list_timelines(Path(args[0]))
    elif cmd == "wait":
        out = {"draft": str(wait_for_draft(Path(args[0]), float(args[1]) if len(args) > 1 else 30))}
    else:
        raise SystemExit(__doc__)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
