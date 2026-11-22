"""Clean copies of video clips, so CapCut plays them exactly as a normal player does.

Why: generated clips (Uvola / Omni Flash, Higgsfield, Veo, phone footage...) are usually H.264 with B-frames. The
MP4 stores the picture with a small built-in delay and an "edit list" telling players to compensate, and AAC audio
carries its own encoder delay. Players honour both, so the file looks perfectly synced; CapCut does not reliably,
so the lips and the sound drift apart on the timeline (found on Uvola 125, 2026-11-20: 2 frames on every clip).

What: a clean copy is the clip exactly as players show it (edit lists applied), re-encoded as H.264 without
B-frames at a constant frame rate, with uncompressed PCM audio, in a .mov with no edit lists. Picture and sound
both start at 0, so every program plays it the same. To cancel the uncompensated AAC delay in CapCut's own exports
(AUDIO_LEAD, 47.9 ms) plus any clip-specific lag, the picture is delayed by whole frames (first frame repeated) and
only the sub-frame remainder comes off the audio, so no sound is ever lost. Copies are cached in `_clean/` next to the source and remade
when the source changes. Images, audio-only files and clips with transparency (overlays) are left alone; so are
files that are already clean. If cleaning fails, the original path is returned (a build never breaks over it).

CLI (prints JSON):
    check <file> [...]     which files need a clean copy and why
    make <file> [...]      make (or reuse) the clean copies; prints {source: clean path}
Library: ensure_clean(path, extra_lead=0) -> path to use (the clean copy, or the original when it needs none).
extra_lead (seconds): a clip's own voice-after-lips lag, cancelled on top of the CapCut fix. Plans set it per clip as
"audio_lead"; lip_sync.py sets it from the measured lip lag on plan rows marked "lips": true (Omni Flash ~0.08 s).
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
VERSION = 4          # bump when the clean recipe changes: older copies are remade
# CapCut exports AAC with the encoder's 2112-sample priming and no edit list to skip it (measured on an export,
# Uvola 125, 2026-11-20: every shot's voice 47.9 ms late). Clean copies start their sound this much early so the
# exported video lands the voice back on the lips. Set CLIP_CLEAN_AUDIO_LEAD=0 to turn it off.
AUDIO_LEAD = float(os.environ.get("CLIP_CLEAN_AUDIO_LEAD", 2112 / 44100))
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


def clean_path(path: str, extra_lead: float = 0.0) -> Path:
    """`_clean/<name>.mov`; with a clip-specific extra lead, `_clean/<name>__lead<ms>.mov` (each lead its own copy)."""
    p = Path(path)
    tag = f"__lead{round(extra_lead * 1000)}" if extra_lead else ""
    return p.parent / CLEAN_DIR / (p.stem + tag + ".mov")


def _stamp(path: str) -> dict:
    st = os.stat(path)
    return {"size": st.st_size, "mtime": int(st.st_mtime)}


def make_clean(path: str, out: Path | None = None, extra_lead: float = 0.0) -> Path:
    """Write the clean copy (see the module doc); returns its path."""
    out = Path(out) if out else clean_path(path, extra_lead)
    lead = AUDIO_LEAD + max(0.0, extra_lead)
    out.parent.mkdir(parents=True, exist_ok=True)
    info = _probe(path).get("streams", [])
    v = next(s for s in info if s.get("codec_type") == "video")
    has_audio = any(s.get("codec_type") == "audio" for s in info)
    rate = _rate(v)
    tmp = out.with_name(out.stem + ".tmp.mov")
    # exactly the frames players show, and sound cut/padded to end on the last frame: file length = picture length,
    # so CapCut can never add a frame past the last real picture (source audio often runs ~1 frame longer)
    if v.get("r_frame_rate") == v.get("avg_frame_rate"):      # constant rate: keep every frame, no more, no less
        n = int(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                                "stream=nb_read_frames", "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip() or 0)
    else:                                                       # variable rate (phones): as many frames as the picture lasts
        vd = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration",
                             "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip()
        n = round(float(vd) * float(rate)) if vd and vd != "N/A" else 0
    # sync correction WITHOUT losing sound: the picture is delayed by whole frames (the first frame repeated k times)
    # and only the sub-frame remainder comes off the audio (<1 frame, never a syllable). File time = source audio time,
    # so plans cut by the clip's words (audio time) stay exact.
    k = int(lead * float(rate) + 1e-6) if (has_audio and lead > 0) else 0
    rem = lead - k / float(rate) if has_audio else 0.0
    total = (n + k) if n else 0
    length = total / float(rate) if total else None
    # timescale: an exact multiple of the frame rate (24 -> 24000, 30000/1001 -> 30000)
    ts = rate.numerator * 1000 if rate.denominator == 1 else rate.numerator
    vf = f"fps={rate.numerator}/{rate.denominator}" + (f",tpad=start={k}:start_mode=clone" if k else "")
    af = (f"atrim=start={rem:.6f},asetpts=PTS-STARTPTS," if rem > 1e-6 else "") + (f"apad=whole_dur={length:.6f},atrim=end={length:.6f}" if length else "anull")
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", path, "-map", "0:v:0"] + (["-map", "0:a:0"] if has_audio else []) + [
        "-vf", vf, "-c:v", "libx264", "-crf", "15", "-preset", "slow", "-bf", "0",
        "-pix_fmt", "yuv420p", "-video_track_timescale", str(ts)] + (["-frames:v", str(total)] if total else []) + (
        ["-c:a", "pcm_s16le", "-ar", "48000", "-af", af] if has_audio else []) + [
        "-use_editlist", "0", str(tmp)]
    subprocess.run(cmd, check=True, capture_output=True)
    tmp.replace(out)
    out.with_suffix(".json").write_text(json.dumps({"source": str(path), "v": VERSION, "audio_lead": lead, **_stamp(path)}))
    return out


def ensure_clean(path: str, extra_lead: float = 0.0) -> str:
    """The path to put on a CapCut timeline: the (cached) clean copy, or the original when it needs none."""
    try:
        if not reasons(path):
            return path
        extra_lead = max(0.0, float(extra_lead or 0.0)); lead = AUDIO_LEAD + extra_lead
        out = clean_path(path, extra_lead); side = out.with_suffix(".json")
        if out.exists() and side.exists():
            try:
                meta = json.loads(side.read_text())
                if meta.get("v") == VERSION and abs(meta.get("audio_lead", -1) - lead) < 1e-9 and meta.get("size") == _stamp(path)["size"] and meta.get("mtime") == _stamp(path)["mtime"]:
                    return str(out)
            except Exception:
                pass
        return str(make_clean(path, out, extra_lead))
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
