"""/edit-mo-to:rehearse prep: turn the editor's own raw video into everything a 10-second showcase edit needs.

CLI (prints a short JSON summary; full detail in <out>/prepare.json):
    rehearse.py prepare <raw video> [--out <folder>] [--seconds 10] [--start S]

Steps (all on this computer):
1. probe the clip (size, fps, rotation, length) and transcribe it (cached);
2. cut dead air tight (pauses over 0.3 s down to a 0.15 s breath) and the recommended stutters/retakes
   (speech_cuts.py), so the 10 s are all talk;
3. pick the 10 s window: from the first sentence start (or --start, in cut-timeline seconds), whole frames;
4. A-roll `segs` for a frame-based plan (plan_build.py format), and the window's words with frame numbers,
   so every graphic can land on its spoken word;
5. a palette taken from the video itself (dark / light / accent), for graphics that match the footage;
6. the speaker's box on the 1080x1920 canvas (from a person cutout of one frame), so graphics avoid the face;
7. a license-free music bed with clear beats (synthesized here) and its beat times;
8. `other_moments`: source times outside the window, for phone-cards (the editor's own clips in phone frames).
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FPS = 30
W, H = 1080, 1920


def _ff(*args):
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *map(str, args)], check=True)


def probe(path: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,r_frame_rate:stream_side_data=rotation:format=duration", "-of", "json",
                        str(path)], capture_output=True, text=True)
    d = json.loads(r.stdout or "{}")
    s = (d.get("streams") or [{}])[0]
    rot = next((int(x.get("rotation", 0)) for x in s.get("side_data_list", []) if "rotation" in x), 0)
    w, h = s.get("width", 0), s.get("height", 0)
    if abs(rot) == 90:
        w, h = h, w
    num, den = (s.get("r_frame_rate") or "30/1").split("/")
    return {"width": w, "height": h, "rotation": rot, "fps": round(int(num) / max(1, int(den)), 3),
            "duration": float((d.get("format") or {}).get("duration") or 0), "portrait": h > w}


def _end_for(words: list[dict], s: float, limit: float, seconds: float) -> tuple[float, bool]:
    """Where a window starting at s should end (a finished sentence in its last 15%, else the last whole
    word), and whether that end is a finished sentence."""
    sent = [w["end"] for w in words if s + seconds * 0.85 <= w["end"] <= limit - 0.04
            and w["word"].rstrip().endswith((".", "!", "?"))]
    ends = [w["end"] for w in words if s < w["end"] <= limit - 0.04]
    return min(limit, (sent[-1] if sent else ends[-1] if ends else limit - 0.12) + 0.12), bool(sent)


def pick_window(words: list[dict], total: float, seconds: float = 10.0, start: float | None = None) -> tuple[float, float]:
    """About `seconds` on the cut timeline. Without --start: try every sentence start and keep the window
    whose speech ends on a finished sentence closest to `seconds` (earliest wins a tie)."""
    if start is None:
        starts = [words[0]["start"]] if words else [0.0]
        starts += [w["start"] for p, w in zip(words, words[1:]) if p["word"].rstrip().endswith((".", "!", "?"))]
        best = None
        for st in starts:
            s = max(0.0, st - 0.1)
            if s >= total - 1:
                continue
            limit = min(total, s + seconds)
            b, ends_sentence = _end_for(words, s, limit, seconds)
            full = b - s >= seconds * 0.7
            score = (not (ends_sentence and full), not full, abs(seconds - (b - s)))
            if best is None or score < best[0]:
                best = (score, s, b)
        s, b = (best[1], best[2]) if best else (0.0, min(total, seconds))
    else:
        s = max(0.0, min(start - 0.1, total - seconds))  # a breath before the first word
        b, _ = _end_for(words, s, min(total, s + seconds), seconds)
    return round(s * FPS) / FPS, round(b * FPS) / FPS


def window_segs(keep_segs: list[dict], a: float, b: float) -> list[dict]:
    """Cut-timeline window -> source spans, re-based to frame 0 (back to back, whole frames)."""
    out, frame = [], 0
    for s in keep_segs:
        seg_a, seg_b = s["at"], s["at"] + (s["src_out"] - s["src_in"])
        lo, hi = max(a, seg_a), min(b, seg_b)
        if hi - lo < 1 / FPS:
            continue
        n = round((hi - lo) * FPS)
        out.append({"src_in": round(s["src_in"] + (lo - seg_a), 4), "from": frame, "to": frame + n})
        frame += n
    return out


def palette(frames: list[Path]) -> dict:
    """Dark / light / accent picked from the footage itself."""
    import colorsys

    from PIL import Image

    px = []
    for f in frames:
        img = Image.open(f).convert("RGB").resize((120, 214))
        q = img.quantize(colors=8).convert("RGB")
        px += list(q.get_flattened_data() if hasattr(q, "get_flattened_data") else q.getdata())
    from collections import Counter

    common = [c for c, _ in Counter(px).most_common(24)]
    lum = lambda c: 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    sat = lambda c: colorsys.rgb_to_hsv(*(v / 255 for v in c))[1]
    dark = min(common, key=lum)
    light = max(common, key=lum)
    accent = max(common, key=lambda c: sat(c) * (0.4 + min(lum(c), 200) / 255))
    # deepen the dark and brighten the accent a little, so text on them stays readable
    dark = tuple(int(v * 0.55) for v in dark)
    h, s, v = colorsys.rgb_to_hsv(*(x / 255 for x in accent))
    accent = tuple(int(x * 255) for x in colorsys.hsv_to_rgb(h, max(s, 0.55), max(v, 0.85)))
    hexc = lambda c: "#%02x%02x%02x" % c
    return {"dark": hexc(dark), "light": hexc(light), "accent": hexc(accent)}


def person_box(frame: Path, work: Path) -> dict | None:
    """Speaker's bounding box on the 1080x1920 canvas, plus an estimated face box (top of the person)."""
    import motion_render as mr
    from PIL import Image

    cut = work / "person.png"
    env_cmd = [str(mr.HF_BIN), "remove-background", str(frame), "-o", str(cut)]
    r = subprocess.run(env_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       shell=sys.platform == "win32")
    if r.returncode != 0 or not cut.exists():
        return None
    alpha = Image.open(cut).convert("RGBA").split()[-1].point(lambda v: 255 if v > 128 else 0)
    box = alpha.getbbox()
    if not box:
        return None
    sx, sy = W / alpha.width, H / alpha.height
    x0, y0, x1, y1 = box
    # the head is the narrow top of the silhouette: measure its width a little below the crown
    row = alpha.crop((0, y0 + max(2, (y1 - y0) // 14), alpha.width, y0 + max(3, (y1 - y0) // 14) + 1)).getbbox()
    hx0, hx1 = (row[0], row[2]) if row else (x0, x1)
    hw = hx1 - hx0
    face = [hx0 - hw * 0.1, y0, hx1 + hw * 0.1, y0 + hw * 1.45]
    sc = lambda b: [round(b[0] * sx), round(b[1] * sy), round(b[2] * sx), round(b[3] * sy)]
    return {"person": sc(box), "face": sc(face)}


def music(out: Path, seconds: float = 12, bpm: int = 100):
    """Soft pad plus a gentle kick on every beat (license-free, made here)."""
    beat = 60 / bpm
    pad = "0.05*sin(2*PI*220*t)+0.04*sin(2*PI*277.18*t)+0.04*sin(2*PI*329.63*t)+0.03*sin(2*PI*110*t)"
    kick = f"0.45*sin(2*PI*(60+90*exp(-mod(t,{beat:.6f})*30))*t)*exp(-mod(t,{beat:.6f})*12)"
    _ff("-f", "lavfi", "-i", f"aevalsrc='{pad}+{kick}':s=44100:d={seconds}", "-ac", "2", out)
    return [round(i * beat, 3) for i in range(int(seconds / beat) + 1)]


def prepare(raw: Path, out: Path, seconds: float = 10.0, start: float | None = None) -> dict:
    import speech_cuts as sc
    from media_timing import _load_16k, to_sf, transcribe

    out.mkdir(parents=True, exist_ok=True)
    info = probe(raw)
    if info["duration"] < seconds + 1:
        raise SystemExit(f"the clip is {info['duration']:.1f}s; send one at least {seconds + 2:.0f}s long")
    words = transcribe(raw)
    if not words:
        raise SystemExit("no speech found; rehearse needs a clip of someone talking")
    data = sc.propose(raw, words, _load_16k(raw), gap=0.3, breath=0.15)
    cut = sc.apply(data, approve=set(), reject=set())
    a, b = pick_window(cut["words"], cut["cut_duration"], seconds, start)
    segs = window_segs(cut["segs"], a, b)
    win_words = [{"word": w["word"], "start": round(w["start"] - a, 3), "end": round(w["end"] - a, 3),
                  "from": round((w["start"] - a) * FPS), "to": round((w["end"] - a) * FPS)}
                 for w in cut["words"] if a <= w["start"] < b]
    used = [(s["src_in"], s["src_in"] + (s["to"] - s["from"]) / FPS) for s in segs]
    other = [round(t, 2) for t in [x * info["duration"] / 8 for x in range(1, 8)]
             if all(not (u0 - 1.5 <= t <= u1 + 1.5) for u0, u1 in used)][:4]
    work = Path(tempfile.mkdtemp(prefix="emt-rehearse-"))
    try:
        frames = []
        for i, s in enumerate(segs[:3]):
            f = work / f"f{i}.png"
            _ff("-ss", s["src_in"] + 0.2, "-i", raw, "-frames:v", 1, "-vf",
                f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2", f)
            frames.append(f)
        pal = palette(frames)
        box = person_box(frames[0], work)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    beats = music(out / "music.wav", seconds + 2)
    res = {
        "raw": str(raw), "clip": info, "out": str(out), "window_cut_timeline": [a, b],
        "removed": {"dead_air_s": round(sum(c["cut"][1] - c["cut"][0] for c in data["candidates"]
                                            if c["type"] in ("pause", "head", "tail") and c["id"] in cut["applied"]), 2),
                    "mistakes": [{"type": c["type"], "removes": c.get("removes"), "keeps": c.get("keeps")}
                                 for c in data["candidates"] if c["type"] not in ("pause", "head", "tail")
                                 and c["id"] in cut["applied"]]},
        "plan_segs": [[raw.name, s["src_in"], s["from"], s["to"], 1.0] for s in segs],
        "clips_dir": str(raw.parent).replace("\\", "/") + "/",
        "frames": segs[-1]["to"] if segs else 0,
        "words": win_words, "text": " ".join(w["word"] for w in win_words),
        "palette": pal, "speaker": box, "other_moments": other,
        "music": {"file": str(out / "music.wav"), "beats": beats},
    }
    (out / "prepare.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"prepare": str(out / "prepare.json"), "window": f"{to_sf(a)}–{to_sf(b)}", "frames": res["frames"],
            "text": res["text"], "dead_air_removed": res["removed"]["dead_air_s"],
            "mistakes_cut": len(res["removed"]["mistakes"]), "palette": pal, "speaker": box}


def main(argv: list[str]) -> None:
    argv = list(argv)
    if len(argv) < 2 or argv[0] != "prepare":
        raise SystemExit(__doc__)
    opt = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
    raw = Path(argv[1])
    out = opt("--out")
    if out is None:
        from machine import PATHS
        out = Path(PATHS["root"]) / "_rehearse" / raw.stem.replace(" ", "_")
    st = opt("--start")
    print(json.dumps(prepare(raw, Path(out), float(opt("--seconds", 10)), float(st) if st else None),
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main(sys.argv[1:])
