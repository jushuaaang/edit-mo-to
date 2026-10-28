"""Copy the newest matching download into a job's file ("Generate for me": a picture or clip Claude just downloaded
from Google Flow in the editor's Chrome). Standard library only.

    collect_download.py "<video folder>" <target> [--downloads DIR] [--within MIN] [--replace]

<target> is relative to the video folder (or absolute inside it), e.g. storyboard/SB-5.png or clips/V01_L02.mp4.
Its extension picks the kind: a picture (png jpg jpeg webp), a video (mp4 mov m4v webm) or audio (mp3 wav m4a).
The newest file of that kind in the Downloads folder (default ~/Downloads; hidden and unfinished .crdownload / .part /
.download files skipped), saved within the last --within minutes (default 30), is copied (the download stays). The
copy keeps the downloaded file's extension (SB-5.png + a .jpg download -> SB-5.jpg). An existing file is never
overwritten without --replace; with it, the same-name files of that kind are replaced, so a keyframe keeps one file.

The target is checked where it really lands (its folder resolved, symlinks followed): it must be in storyboard/,
clips/, vo/, music/, refs/ or the job card's clips_folder, inside the video folder. Refused: a folder without
.edit-mo-to/job.json, a target outside those (.., another path, a symlinked subfolder leading out or into
.edit-mo-to/), an unknown extension. The copy goes through a new .part file (an existing one, even a planted symlink,
is removed first; then O_CREAT|O_EXCL|O_NOFOLLOW). Prints {"ok": true, "path", "from"} or {"ok": false, "error"}
(exit 1).
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


def open_new(part: Path):
    """Open part for writing as a brand-new file: a file or symlink already there (e.g. one planted to lead out of
    the folder) is removed first (unlink never follows a link), then O_CREAT|O_EXCL (|O_NOFOLLOW where the system has
    it) refuses anything that appears in between. Without O_NOFOLLOW (Windows), an lstat check runs first."""
    part.unlink(missing_ok=True)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not nofollow and os.path.lexists(part):
        raise Refused(f"{part.name} appeared while saving; try again")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow | getattr(os, "O_BINARY", 0)
    return os.fdopen(os.open(part, flags, 0o644), "wb")


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


ALLOWED = ("storyboard", "clips", "vo", "music", "refs")   # subfolders a generated file may go in


def _allowed_dirs(folder: Path) -> list:
    """storyboard/, clips/, vo/, music/, refs/ and the job card's clips_folder when it is inside the folder."""
    dirs = [folder / d for d in ALLOWED]
    try:
        card = json.loads((folder / ".edit-mo-to" / "job.json").read_text(encoding="utf-8")).get("card") or {}
        raw = card.get("clips_folder")
        if isinstance(raw, str) and raw.strip():
            clips = Path(raw)
            dirs.append((clips if clips.is_absolute() else folder / clips).resolve())
    except (OSError, ValueError, AttributeError):
        pass
    return dirs


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
    real = target.parent.resolve() / target.name     # where it really lands (symlinked subfolders followed)
    if not _inside(real, folder):
        raise Refused("the target must be inside the video folder")
    if ".edit-mo-to" in real.relative_to(folder).parts:
        raise Refused("the target can't be in .edit-mo-to/")
    if not any(_inside(real.parent, d) for d in _allowed_dirs(folder) if _inside(d, folder)):
        raise Refused(f"the target must be in one of {', '.join(d + '/' for d in ALLOWED)} or the job's clips folder")
    return real, kind


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
        with src.open("rb") as fin, open_new(part) as fout:
            shutil.copyfileobj(fin, fout)
        os.replace(part, dest)
    except FileExistsError:
        raise Refused("a file appeared while saving; nothing was saved") from None
    finally:
        part.unlink(missing_ok=True)
    if dest.is_symlink() or not _inside(dest.resolve(), folder.resolve()):
        dest.unlink(missing_ok=True)
        raise Refused("the saved file led outside the video folder; removed it")
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
