"""Copy the newest matching download into a job's file ("Generate for me": a picture or clip Claude just downloaded
from Google Flow in the editor's Chrome). Standard library only.

    collect_download.py "<video folder>" <target> [--downloads DIR] [--within MIN] [--replace]

<target> is relative to the video folder (or absolute inside it), e.g. storyboard/SB-5.png or clips/V01_L02.mp4.
Its extension picks the kind: a picture (png jpg jpeg webp), a video (mp4 mov m4v webm) or audio (mp3 wav m4a).
The newest file of that kind in the Downloads folder (default ~/Downloads; hidden and unfinished .crdownload / .part /
.download files skipped), saved within the last --within minutes (default 30), is copied (the download stays). The
copy keeps the downloaded file's extension (SB-5.png + a .jpg download -> SB-5.jpg). An existing file is never
overwritten without --replace; with it, the same-name files of that kind are replaced, so a keyframe keeps one file.

Refused: a folder without .edit-mo-to/job.json, a target outside the video folder (.., another path, a symlinked
subfolder leading out) or inside .edit-mo-to/, an unknown extension. Prints {"ok": true, "path", "from"} or
{"ok": false, "error"} (exit 1).
"""
import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

KINDS = {"picture": {".png", ".jpg", ".jpeg", ".webp"}, "video": {".mp4", ".mov", ".m4v", ".webm"},
         "audio": {".mp3", ".wav", ".m4a"}}
UNFINISHED = {".crdownload", ".part", ".download", ".tmp"}


class Refused(Exception):
    pass


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def target_path(folder: Path, raw: str) -> "tuple[Path, set]":
    folder = folder.resolve()
    if not (folder / ".edit-mo-to" / "job.json").is_file():
        raise Refused(f"{folder} is not a video folder with a job")
    rel = Path(raw)
    if ".." in rel.parts or raw.endswith(("/", "\\")):
        raise Refused("the target must be a file inside the video folder")
    target = rel if rel.is_absolute() else folder / rel
    kind = next((exts for exts in KINDS.values() if target.suffix.lower() in exts), None)
    if kind is None:
        raise Refused(f"unknown file type {target.suffix or '(none)'}: use a picture, video or audio name")
    if not _inside(target.parent.resolve(), folder) or not _inside(target.absolute(), folder):
        raise Refused("the target must be inside the video folder")
    if ".edit-mo-to" in target.absolute().relative_to(folder).parts:
        raise Refused("the target can't be in .edit-mo-to/")
    return target, kind


def newest(downloads: Path, kind: set, within_min: float) -> Path:
    since = time.time() - within_min * 60
    best = None
    try:
        entries = list(downloads.iterdir())
    except OSError as e:
        raise Refused(f"can't read the Downloads folder {downloads}") from e
    for p in entries:
        if p.name.startswith(".") or p.suffix.lower() in UNFINISHED or p.suffix.lower() not in kind:
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        if p.is_file() and st.st_mtime >= since and (best is None or st.st_mtime > best[0]):
            best = (st.st_mtime, p)
    if best is None:
        raise Refused(f"no new download of that kind in the last {within_min:g} minutes in {downloads}")
    return best[1]


def collect(folder: Path, raw: str, downloads: Path, within_min: float, replace: bool) -> dict:
    target, kind = target_path(folder, raw)
    src = newest(downloads, kind, within_min)
    dest = target.with_suffix(src.suffix.lower())
    same = [target.with_suffix(ext) for ext in kind]
    taken = [p for p in same if p.exists() or p.is_symlink()]
    if taken and not replace:
        raise Refused(f"{taken[0].name} already exists; pass --replace to replace it")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not _inside(dest.parent.resolve(), folder.resolve()):
        raise Refused("the target must be inside the video folder")
    part = dest.with_name(f".{dest.name}.part")
    try:
        shutil.copyfile(src, part)
        os.replace(part, dest)
    finally:
        part.unlink(missing_ok=True)
    for p in same:
        if p != dest and (p.exists() or p.is_symlink()):
            p.unlink()
    return {"path": dest.resolve().as_posix(), "from": src.name}


def main(argv=None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("folder")
    p.add_argument("target")
    p.add_argument("--downloads", default=str(Path.home() / "Downloads"))
    p.add_argument("--within", type=float, default=30.0, help="minutes (default 30)")
    p.add_argument("--replace", action="store_true")
    a = p.parse_args(argv)
    try:
        result = collect(Path(a.folder), a.target, Path(a.downloads), a.within, a.replace)
    except (Refused, OSError) as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        sys.exit(1)
    print(json.dumps({"ok": True, **result}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
