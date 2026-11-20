"""Clean copies of video clips, so CapCut plays them exactly as a normal player does.

Why: generated clips (Uvola / Omni Flash, Higgsfield, Veo, phone footage...) are usually H.264 with B-frames. The
MP4 stores the picture with a small built-in delay and an "edit list" telling players to compensate, and AAC audio
carries its own encoder delay. Players honour both, so the file looks perfectly synced; CapCut does not reliably,
so the lips and the sound drift apart on the timeline (found on Uvola 125, 2026-11-20: 2 frames on every clip).

What: a clean copy is the clip exactly as players show it (edit lists applied), re-encoded as H.264 without
B-frames at a constant frame rate, with uncompressed PCM audio, in a .mov with no edit lists. Picture and sound
both start at 0, so every program plays it the same. Copies are cached in `_clean/` next to the source and remade
when the source changes. Images, audio-only files and clips with transparency (overlays) are left alone; so are
files that are already clean. If cleaning fails, the original path is returned (a build never breaks over it).

CLI (prints JSON):
    check <file> [...]     which files need a clean copy and why
    make <file> [...]      make (or reuse) the clean copies; prints {source: clean path}
Library: ensure_clean(path) -> path to use (the clean copy, or the original when it needs none).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mts", ".m2ts", ".3gp"}
CLEAN_DIR = "_clean"
STANDARD_RATES = [Fraction(24000, 1001), Fraction(24), Fraction(25), Fraction(30000, 1001), Fraction(30),
                  Fraction(50), Fraction(60000, 1001), Fraction(60)]


def _probe(path: str) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=index,codec_type,codec_name,profile,pix_fmt,has_b_frames,r_frame_rate,avg_frame_rate",
                          "-of", "json", path], capture_output=True, text=True)
    return json.loads(out.stdout or "{}")


def _has_edit_list(path: str) -> bool:
    """True when an MP4/MOV edit list shifts a stream (media time > 0), i.e. players compensate a hidden delay."""
    trace = subprocess.run(["ffprobe", "-v", "trace", "-i", path], capture_output=True, text=True).stderr
    for line in trace.splitlines():
        if "edit list" in line and "media time:" in line:
            try:
                if int(line.split("media time:")[1].split(",")[0].strip()) > 0:
                    return True
            except ValueError:
                continue
    return False


def _rate(v: dict) -> Fraction:
    def frac(s):
        try:
            n, d = s.split("/"); return Fraction(int(n), int(d)) if int(d) else Fraction(0)
        except Exception:
            return Fraction(0)
    r, avg = frac(v.get("r_frame_rate", "0/1")), frac(v.get("avg_frame_rate", "0/1"))
    rate = r if r and (not avg or abs(float(r - avg)) < 0.01) else (avg or r or Fraction(30))
    return min(STANDARD_RATES, key=lambda s: abs(float(s - rate))) if any(abs(float(s - rate)) < 0.05 for s in STANDARD_RATES) else rate


def reasons(path: str) -> list[str]:
    """Why this file needs a clean copy ([] = it doesn't)."""
    p = Path(path)
    if p.suffix.lower() not in VIDEO_EXT or not p.exists() or p.parent.name == CLEAN_DIR:
        return []
    info = _probe(str(p)).get("streams", [])
    v = next((s for s in info if s.get("codec_type") == "video"), None)
    if not v:
        return []
    pix = v.get("pix_fmt") or ""
    if pix.startswith(("yuva", "rgba", "bgra", "argb", "abgr", "gbrap", "ya")) or (v.get("codec_name") == "prores" and "4444" in (v.get("profile") or "")):
        return []                                           # has transparency (overlay): leave it alone
    why = []
    if int(v.get("has_b_frames") or 0) > 0:
        why.append("B-frames")
    if _has_edit_list(str(p)):
        why.append("edit list")
    if v.get("r_frame_rate") != v.get("avg_frame_rate"):
        why.append("variable frame rate")
    a = next((s for s in info if s.get("codec_type") == "audio"), None)
    if a and not (a.get("codec_name") or "").startswith("pcm_"):
        why.append(f"{a.get('codec_name')} audio delay")
    return why


def clean_path(path: str) -> Path:
    p = Path(path)
    return p.parent / CLEAN_DIR / (p.stem + ".mov")


def _stamp(path: str) -> dict:
    st = os.stat(path)
    return {"size": st.st_size, "mtime": int(st.st_mtime)}


def make_clean(path: str, out: Path | None = None) -> Path:
    """Write the clean copy (see the module doc); returns its path."""
    out = Path(out) if out else clean_path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    info = _probe(path).get("streams", [])
    v = next(s for s in info if s.get("codec_type") == "video")
    has_audio = any(s.get("codec_type") == "audio" for s in info)
    rate = _rate(v)
    tmp = out.with_name(out.stem + ".tmp.mov")
    # timescale: an exact multiple of the frame rate (24 -> 24000, 30000/1001 -> 30000)
    ts = rate.numerator * 1000 if rate.denominator == 1 else rate.numerator
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", path, "-map", "0:v:0"] + (["-map", "0:a:0"] if has_audio else []) + [
        "-vf", f"fps={rate.numerator}/{rate.denominator}", "-c:v", "libx264", "-crf", "15", "-preset", "slow", "-bf", "0",
        "-pix_fmt", "yuv420p", "-video_track_timescale", str(ts)] + (["-c:a", "pcm_s16le", "-ar", "48000"] if has_audio else []) + [
        "-use_editlist", "0", str(tmp)]
    subprocess.run(cmd, check=True, capture_output=True)
    tmp.replace(out)
    out.with_suffix(".json").write_text(json.dumps({"source": str(path), **_stamp(path)}))
    return out


def ensure_clean(path: str) -> str:
    """The path to put on a CapCut timeline: the (cached) clean copy, or the original when it needs none."""
    try:
        if not reasons(path):
            return path
        out = clean_path(path); side = out.with_suffix(".json")
        if out.exists() and side.exists():
            try:
                meta = json.loads(side.read_text())
                if meta.get("size") == _stamp(path)["size"] and meta.get("mtime") == _stamp(path)["mtime"]:
                    return str(out)
            except Exception:
                pass
        return str(make_clean(path, out))
    except Exception as e:                                   # never break a build over this
        print(f"clip_clean: kept original for {path}: {e}", file=sys.stderr)
        return path


def main(argv: list[str]) -> None:
    if len(argv) < 2 or argv[0] not in ("check", "make"):
        raise SystemExit(__doc__)
    if argv[0] == "check":
        print(json.dumps({f: reasons(f) for f in argv[1:]}, indent=1))
    else:
        print(json.dumps({f: ensure_clean(f) for f in argv[1:]}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
