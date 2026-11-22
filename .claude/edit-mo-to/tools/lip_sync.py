"""Lip sync for AI talking clips (Omni Flash, Veo, Higgsfield...): time them by their LIPS, not by their voice.

Why (Revella / Uvola 125, 2026-11-20..22): plans placed talking clips by ASR word times (often 0.15-0.35 s off), and
an AI clip's own voice trails its lips (~0.03-0.1 s, Omni Flash ~0.085 s), which only a per-clip `audio_lead`
cancels; nothing set it, so exports read as "lips early" or "lips late".

What, for every plan clip marked `"lips": true` (plan_tools.py expand runs this on its own):
  1. place: the clip's own voice is matched to the VO under it by audio-envelope cross-correlation (within
     +-0.5 s of the planned src_in, the cut and the speed stay); src_in moves to the best match, whole 30 fps frames.
  2. lips: the clip's voice-after-lips lag is measured from mouth openness (Apple Vision on a Mac: `lipopen.swift`,
     compiled on first use; MediaPipe Face Landmarker elsewhere, e.g. Windows; LIP_SYNC_ENGINE forces one) and
     becomes the clip's `audio_lead` (rounded so the clean copy's picture delay is whole
     source frames and its sound is never trimmed: file time = source time). Unmeasurable (no face, no tracker,
     weak match) -> DEFAULT_LAG.
  clip_clean then delays the picture by CapCut's export sound delay + that lag, so in the exported video the lips
  sit on the heard voice. A row that gives `audio_lead` itself keeps it; `"lips_place": false` skips step 1.

CLI (prints JSON):
    lag <clip> [...]               each clip's voice-after-lips lag (s), how sure, and the audio_lead it gets
    sync <plan.json> [--out f]     steps 1-2 on a contract plan (default: in place); prints the report
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import clip_clean  # noqa: E402

DEFAULT_LAG = 0.08        # Omni Flash raw voice-after-lips (Uvola 125 0.08, Revella median ~0.083)
LAG_RANGE = (-0.05, 0.2)  # a measured lag outside this is a bad match, not a real lag
MIN_R, MIN_SHARP = 0.55, 0.3
SEARCH = 0.5              # placement search, seconds either side of the planned src_in
MIN_PLACE_R = 0.5
MIN_PLACE_MARGIN = 0.1   # the best match must beat any rival match more than 0.12 s away by this much
STEP = 0.01               # placement envelope step (s)


# --- audio envelopes ------------------------------------------------------------------------------------------
def _pcm(path: str, sr: int) -> np.ndarray:
    b = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
                       capture_output=True).stdout
    return np.frombuffer(b, np.int16).astype(np.float32)


_env_cache: dict = {}


def envelope(path: str) -> np.ndarray:
    """Syllable rhythm every STEP seconds (time i*STEP): log RMS, lightly smoothed, with loudness trends longer
    than 0.4 s removed (otherwise one long speech block matches equally well anywhere inside it)."""
    if path not in _env_cache:
        sr = 8000; a = _pcm(path, sr); n = int(sr * STEP); m = len(a) // n
        if m < 50:
            _env_cache[path] = np.zeros(max(m, 1))
        else:
            e = np.convolve(np.log(np.sqrt((a[: m * n].reshape(m, n) ** 2).mean(1)) + 20), np.ones(3) / 3, "same")
            _env_cache[path] = _hp(e, 40)
    return _env_cache[path]


def _z(x: np.ndarray) -> np.ndarray:
    return (x - x.mean()) / (x.std() + 1e-9)


def _at(env: np.ndarray, times: np.ndarray) -> np.ndarray:
    return env[np.clip(np.round(np.asarray(times) / STEP).astype(int), 0, len(env) - 1)]


def best_offset(vo_env: np.ndarray, clip_env: np.ndarray, vo_t0: float, src_in: float, dur: float, speed: float,
                search: float = SEARCH, clip_len: float | None = None) -> tuple[float, float] | None:
    """Offset d (s, source time) so the clip played from src_in + d matches the VO from vo_t0 best: (d, r).
    None when the clip has no speech there."""
    t = np.arange(0.0, dur, STEP)
    if len(t) < 20:
        return None
    v = _at(vo_env, vo_t0 + t)
    if v.std() < 0.05:
        return None
    ds, rs = [], []
    for d in np.arange(-search, search + 1e-9, STEP):
        s0 = src_in + d
        if s0 < -1e-9 or (clip_len is not None and s0 + dur * speed > clip_len + 0.02):
            continue
        c = _at(clip_env, s0 + t * speed)
        if c.std() < 0.05:
            continue
        ds.append(float(d)); rs.append(float(np.dot(_z(v), _z(c)) / len(t)))
    if not rs:
        return None
    i = int(np.argmax(rs))
    # how clearly it wins: best r minus the best r of any offset more than 0.12 s away (a second, rival match)
    rival = max((r for d, r in zip(ds, rs) if abs(d - ds[i]) > 0.12), default=-1.0)
    edge = i in (0, len(rs) - 1)
    return round(ds[i], 3), rs[i], float(rs[i] - rival), edge


# --- lips (Apple Vision, macOS) --------------------------------------------------------------------------------------
def _cache_dir() -> Path:
    try:
        from machine import TMP
        d = Path(TMP) / "cache" / "lip_sync"
    except Exception:
        d = Path.home() / ".cache" / "edit-mo-to-lip_sync"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _lipopen() -> str | None:
    """The compiled Vision mouth-openness tool (macOS only), built from lipopen.swift when missing or older."""
    if sys.platform != "darwin":
        return None
    src = TOOLS / "lipopen.swift"
    exe = _cache_dir() / "lipopen"
    if not exe.exists() or exe.stat().st_mtime < src.stat().st_mtime:
        r = subprocess.run(["swiftc", "-O", str(src), "-o", str(exe)], capture_output=True, text=True)
        if r.returncode:
            print(f"lip_sync: cannot build lipopen: {r.stderr[-300:]}", file=sys.stderr)
            return None
    return str(exe)


def _hp(x: np.ndarray, k: int) -> np.ndarray:
    return x - np.convolve(x, np.ones(k) / k, "same")


def lag_from_curves(ts: np.ndarray, op: np.ndarray, audio: np.ndarray, sr: int = 16000) -> dict | None:
    """Voice-after-lips lag from mouth openness (per frame) and the clip's audio: {lag, r, sharp} or None.
    lag > 0 = the voice comes after the lips."""
    ok = op > 0
    if len(ts) < 24 or ok.mean() < 0.6:
        return None
    hop = sr // 200; n = len(audio) // hop                         # 5 ms grid
    if n < 100:
        return None
    e = np.convolve(np.log(np.sqrt((audio[: n * hop].reshape(n, hop) ** 2).mean(1)) + 30), np.ones(12) / 12, "same")
    e = _hp(e, 80)                                                 # drop > 0.4 s loudness trends
    g = np.arange(0, ts[-1], 0.005)
    vo = _hp(np.convolve(np.interp(g, ts[ok], op[ok]), np.ones(12) / 12, "same"), 80)
    Ls = np.arange(-0.15, 0.3001, 0.005); rs = []
    for L in Ls:
        j = int(round(L / 0.005)); lo = max(0, -j); hi = min(len(g), n - j)
        if hi - lo < 50:
            rs.append(-1.0); continue
        rs.append(float(np.dot(_z(vo[lo:hi]), _z(e[lo + j:hi + j]))) / (hi - lo))
    rs = np.array(rs); i = int(np.argmax(rs))
    if i in (0, len(Ls) - 1):
        return None
    j = int(0.1 / 0.005)
    side = np.mean([rs[max(0, i - j)], rs[min(len(rs) - 1, i + j)]])
    return {"lag": round(float(Ls[i]), 3), "r": round(float(rs[i]), 2), "sharp": round(float(rs[i] - side), 2)}


# --- lips (MediaPipe: Windows, or a Mac without Vision) -----------------------------------------------------------
MP_MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/"
                "face_landmarker.task")
MP_WIDTH = 360            # frames are measured at this width (the face is large in talking clips; keeps it fast)


def _mp_model() -> str:
    """MediaPipe's face landmark model, downloaded once into the cache from Google's model store."""
    f = _cache_dir() / "face_landmarker.task"
    if not f.exists() or f.stat().st_size < 1_000_000:
        import urllib.request
        tmp = f.with_suffix(".part")
        urllib.request.urlretrieve(MP_MODEL_URL, tmp)
        tmp.replace(f)
    return str(f)


def _mp_available() -> bool:
    try:
        import mediapipe  # noqa: F401
        return True
    except Exception:
        return False


def _openness_mediapipe(path: str) -> tuple[np.ndarray, np.ndarray]:
    """Per frame (time, mouth height / mouth width of the outer lips; -1 = no face), with MediaPipe Face Landmarker.
    Frames come from ffmpeg (edit lists applied, so times match the audio as players show it)."""
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python import vision
    fps = _fps(path)
    info = clip_clean._probe(path).get("streams", [])
    v = next(x for x in info if x.get("codec_type") == "video")
    w0, h0 = int(v.get("width") or 0), int(v.get("height") or 0)
    if not (w0 and h0):
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                              "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip().split(",")
        w0, h0 = int(out[0]), int(out[1])
    w = MP_WIDTH; h = int(round(h0 * w / w0 / 2)) * 2
    proc = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-an", "-vf", f"scale={w}:{h}",
                             "-pix_fmt", "rgb24", "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    opts = vision.FaceLandmarkerOptions(base_options=BaseOptions(model_asset_path=_mp_model()),
                                        running_mode=vision.RunningMode.VIDEO, num_faces=1)
    ts, op = [], []
    size = w * h * 3
    with vision.FaceLandmarker.create_from_options(opts) as lm:
        i = 0
        while True:
            buf = proc.stdout.read(size)
            if len(buf) < size:
                break
            img = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.frombuffer(buf, np.uint8).reshape(h, w, 3))
            t = i / fps
            res = lm.detect_for_video(img, int(round(t * 1000)))
            val = -1.0
            if res.face_landmarks:
                L = res.face_landmarks[0]
                dy = abs(L[17].y - L[0].y) * h          # outer lips: top of the upper lip to the bottom of the lower
                dx = abs(L[291].x - L[61].x) * w        # mouth corners
                if dx > 0:
                    val = dy / dx
            ts.append(t); op.append(val); i += 1
    proc.wait()
    return np.array(ts), np.array(op)


def _openness_vision(path: str) -> tuple[np.ndarray, np.ndarray] | None:
    exe = _lipopen()
    if not exe:
        return None
    txt = subprocess.run([exe, path], capture_output=True, text=True).stdout.split()
    a = np.array(txt, float).reshape(-1, 3) if txt and len(txt) % 3 == 0 else np.zeros((0, 3))
    return a[:, 0], a[:, 1]


def engine() -> str | None:
    """Which face tracker measures the lips here: LIP_SYNC_ENGINE (vision | mediapipe) if set, else Apple Vision
    on a Mac, else MediaPipe when installed, else None (DEFAULT_LAG)."""
    want = os.environ.get("LIP_SYNC_ENGINE", "").strip().lower()
    if want in ("vision", "mediapipe"):
        return want
    if sys.platform == "darwin" and _lipopen():
        return "vision"
    return "mediapipe" if _mp_available() else None


def measure_lag(path: str, eng: str | None = None) -> dict:
    """{lag, r, sharp, source: "lips"|"default", engine, why?} for one clip (raw source file), cached by size + mtime
    and engine."""
    eng = eng or engine()
    st = os.stat(path)
    key = hashlib.sha1(f"{os.path.abspath(path)}|{st.st_size}|{int(st.st_mtime)}|{eng}|v2".encode()).hexdigest()[:16]
    cache = _cache_dir() / f"{key}.json"
    if cache.exists():
        try:
            return json.loads(cache.read_text())
        except Exception:
            pass
    res = {"lag": DEFAULT_LAG, "source": "default"}
    curves = None
    try:
        curves = (_openness_vision(path) if eng == "vision" else _openness_mediapipe(path) if eng == "mediapipe" else None)
    except Exception as e:                                   # a lip measurement never breaks a plan
        res["why"] = f"{eng} failed: {e}"
        return res                                           # not cached: retried next time
    if curves is None:
        res["why"] = "no face tracker on this machine (install mediapipe)"
    else:
        res["engine"] = eng
        m = lag_from_curves(curves[0], curves[1], _pcm(path, 16000)) if len(curves[0]) else None
        if m is None:
            res["why"] = "no face / no speech to measure"
        elif m["r"] < MIN_R or m["sharp"] < MIN_SHARP or not LAG_RANGE[0] <= m["lag"] <= LAG_RANGE[1]:
            res.update(why=f"weak match (lag {m['lag']:+.3f} r {m['r']} sharp {m['sharp']})", measured=m)
        else:
            res = {**m, "source": "lips", "engine": eng}
    cache.write_text(json.dumps(res))
    return res


def audio_lead_for(lag: float, fps: float) -> float:
    """The clip's `audio_lead` for a voice-after-lips lag: CapCut's export delay + lag, rounded to whole source
    frames (so clip_clean only delays the picture and never trims sound), minus that export delay. 0 when the
    nearest whole frame is not above the export delay alone (the plain clean copy is then the closer match)."""
    k = round((clip_clean.AUDIO_LEAD + max(0.0, lag)) * fps)
    lead = k / fps - clip_clean.AUDIO_LEAD
    return lead if lead > 1e-6 else 0.0          # full precision: rounding would floor clip_clean's frame count


def _fps(path: str) -> float:
    info = clip_clean._probe(path).get("streams", [])
    v = next((s for s in info if s.get("codec_type") == "video"), None)
    return float(clip_clean._rate(v)) if v else 30.0


def _duration(path: str) -> float | None:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return None


# --- the plan pass --------------------------------------------------------------------------------------------
def _f30(x: float) -> float:
    return round(round(x * 30) / 30, 10)


def sync_plan(plan: dict, lag_fn=measure_lag, env_fn=envelope, fps_fn=_fps, dur_fn=_duration) -> list[dict]:
    """Steps 1-2 (module doc) on every `"lips": true` clip of a contract plan, in place. Returns one report row
    per such clip: timeline, at, file, moved_ms (or why it stayed), r, lag_ms, lag_source, audio_lead."""
    rows = []
    for tl in plan.get("timelines", []):
        vo = tl.get("vo")
        for c in tl.get("clips", []):
            if not c.get("lips"):
                continue
            f = c["file"]
            row = {"timeline": tl.get("name"), "at": c["at"], "file": os.path.basename(f)}
            if not os.path.exists(f):
                rows.append({**row, "error": "file not found"}); continue
            speed = float(c.get("speed") or 1.0)
            dur = float(c.get("duration") or (c["src_out"] - c["src_in"]) / speed)
            if vo and c.get("mute", True) and c.get("lips_place", True) and os.path.exists(vo):
                b = best_offset(env_fn(vo), env_fn(f), tl.get("vo_in", 0.0) + c["at"], c["src_in"], dur, speed,
                                clip_len=dur_fn(f))
                if b is None:
                    row["placed"] = "kept: no speech to match"
                elif b[1] < MIN_PLACE_R or b[2] < MIN_PLACE_MARGIN or b[3]:
                    row.update(placed=f"kept: unclear match (best {b[0] * 1000:+.0f} ms, r {b[1]:.2f}, margin {b[2]:.2f}"
                                      + (", at the search edge" if b[3] else "") + "): check by eye", r=round(b[1], 2))
                else:
                    new_in = max(0.0, _f30(c["src_in"] + b[0]))
                    row.update(moved_ms=round((new_in - c["src_in"]) * 1000), r=round(b[1], 2), margin=round(b[2], 2))
                    c["src_in"] = new_in
                    c["src_out"] = _f30(new_in + round(dur * 30) * speed / 30)
            else:
                row["placed"] = "kept: plays its own voice" if not c.get("mute", True) else "kept: no VO / placing off"
            if "audio_lead" not in c:
                m = lag_fn(f)
                c["audio_lead"] = audio_lead_for(m["lag"], fps_fn(f))
                row.update(lag_ms=round(m["lag"] * 1000), lag_source=m["source"], **({"why": m["why"]} if m.get("why") else {}))
            row["audio_lead"] = c["audio_lead"]
            rows.append(row)
    return rows


def main(argv: list[str]) -> None:
    if len(argv) < 2 or argv[0] not in ("lag", "sync"):
        raise SystemExit(__doc__)
    if argv[0] == "lag":
        out = {}
        for f in argv[1:]:
            m = measure_lag(f)
            out[f] = {**m, "audio_lead": audio_lead_for(m["lag"], _fps(f))}
    else:
        src = Path(argv[1])
        dst = Path(argv[argv.index("--out") + 1]) if "--out" in argv else src
        plan = json.loads(src.read_text(encoding="utf-8"))
        rows = sync_plan(plan)
        dst.write_text(json.dumps(plan, indent=1, ensure_ascii=False), encoding="utf-8")
        out = {"plan": str(dst), "clips": rows}
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
