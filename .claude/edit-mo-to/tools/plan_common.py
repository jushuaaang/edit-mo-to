"""Shared plan helpers: frame -> microsecond conversion, sound-cue placement, beat snapping and plan checks.
Used by plan_build.py (re-exported there unchanged) and the other plan tools."""
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
MOTION = TOOLS.parent / "motion"
sys.path.insert(0, str(TOOLS))
import motion_render as mr  # noqa: E402

SFX_TRACKS = ("sfx_a", "sfx_b", "sfx_c")
MERGE_US = 150_000


def US(frame: int) -> int:
    """Frame (30 fps) -> whole microseconds, the unit VectCutAPI stores."""
    return round(frame * 1_000_000 / 30)


def clip_len_f(clip: dict) -> int:
    """A contract clip's timeline length in whole frames: its `duration` (expand writes len_f / 30), else, for
    plans written before clips carried one, the source span over speed (a frame off for some slow clips)."""
    if clip.get("duration") is not None:
        return round(clip["duration"] * 30)
    return round((clip["src_out"] - clip["src_in"]) * 30 / (clip.get("speed") or 1.0))


def clip_volume(clip: dict) -> float:
    """A contract clip's linear volume: 0 when muted, else `volume` (default 1) times the `gain_db` gain."""
    if clip.get("mute", True):
        return 0
    return float(clip.get("volume", 1.0)) * 10 ** (clip.get("gain_db", 0) / 20)


def sfx_cues(overlays: list, end_us: int | None = None) -> list:
    """Sound cues for the overlays: resolved file, start, trimmed length, volume and a track, so that no two
    cues overlap on one track (VectCutAPI refuses overlaps) and none runs past end_us."""
    defaults = json.loads((MOTION / "sfx_defaults.json").read_text(encoding="utf-8"))
    raw = []
    for o in overlays:
        spec = o.get("sfx", "none")
        if spec in (None, "none"):
            continue
        cues = defaults.get(o["template"], []) if spec == "default" else spec
        vars_ = o.get("vars", {})
        try:
            vars_ = {**mr._split(mr.template_text(o["template"]))[0], **vars_}   # offsets may name a default
        except (FileNotFoundError, ValueError):
            pass
        for c in cues:
            cond = c.get("when")
            if cond:
                key, _, val = cond.partition("=")
                if str(vars_.get(key)) != val:
                    continue
            off = c.get("offset", 0)
            # an offset naming a list var ("0.9,1.6,2.4", e.g. cursor-ui's t_clicks) gives one cue per time
            offs = [float(x) for x in str(vars_.get(off, 0)).split(",") if x.strip()] if isinstance(off, str) else [float(off)]
            ln = round(float(c.get("len", 0.6)) * 1_000_000)
            ov_end = US(o["to"])
            for off in offs:
                at = US(o["from"]) + round(off * 1_000_000)
                if at >= ov_end:
                    continue
                raw.append({"file": str(MOTION / "sfx" / f"{c['name']}.mp3"), "at_us": at, "len_us": ln,
                            "volume": float(c.get("volume", 0.5))})
    raw.sort(key=lambda c: c["at_us"])
    # two whooshes landing together (a flash and a title on the same beat) sound muddy: keep the first
    kept = []
    for c in raw:
        if "whoosh" in Path(c["file"]).stem and any(
                "whoosh" in Path(k["file"]).stem and abs(c["at_us"] - k["at_us"]) <= MERGE_US for k in kept):
            continue
        kept.append(c)
    raw = kept
    free = {t: 0 for t in SFX_TRACKS}
    out = []
    for c in raw:
        if end_us is not None:
            if c["at_us"] >= end_us:
                continue
            c["len_us"] = min(c["len_us"], end_us - c["at_us"])
        track = next((t for t in SFX_TRACKS if free[t] <= c["at_us"]), None)
        if track is None:
            # all tracks still sounding: cut the cue that ends first so the new one lands on its beat
            # (a sound arriving late reads worse than one cut short)
            track = min(free, key=free.get)
            prev = next(p for p in reversed(out) if p["track"] == track)
            if c["at_us"] - prev["at_us"] < 50_000:
                continue
            prev["len_us"] = c["at_us"] - prev["at_us"]
        free[track] = c["at_us"] + c["len_us"]
        out.append({**c, "track": track})
    return out


def beat_snap(overlays: list, beats: list, tol: int = 3, music_at: int = 0, tracks=None) -> list:
    """Snap overlay starts (frames, 30 fps) to the nearest beat within tol frames, in place; lengths are kept.
    beats are seconds from the music's start, which sits at timeline frame music_at. Returns the moves."""
    frames = sorted({music_at + round(b * 30) for b in beats})
    moves = []
    for i, o in enumerate(overlays):
        if o.get("snap") is False or not frames or (tracks and o.get("track") not in tracks):
            continue
        near = min(frames, key=lambda f: abs(f - o["from"]))
        shift = near - o["from"]
        if shift == 0 or abs(shift) > tol or near < 0:
            continue
        moves.append({"index": i, "template": o.get("template"), "from": o["from"], "to": near})
        o["from"], o["to"] = near, o["to"] + shift
    return moves


def check_plan(plan: dict) -> list[str]:
    """Problems CapCut would refuse, found before anything renders: overlays overlapping on one track,
    tracks without a layer index, segs with gaps or overlaps."""
    errs, by_track = [], {}
    for i, o in enumerate(plan.get("overlays", []), 1):
        if o["track"] not in plan.get("tracks", {}):
            errs.append(f"overlay {i} ({o['template']}) uses track '{o['track']}', which has no index in plan.tracks")
        if o["to"] <= o["from"]:
            errs.append(f"overlay {i} ({o['template']}) ends before it starts")
        by_track.setdefault(o["track"], []).append((o["from"], o["to"], i, o["template"]))
    for t, items in by_track.items():
        items.sort()
        for (a0, a1, ai, at), (b0, b1, bi, bt) in zip(items, items[1:]):
            if b0 < a1:
                errs.append(f"track '{t}': overlay {ai} ({at}, {a0}-{a1}) overlaps overlay {bi} ({bt}, {b0}-{b1}); "
                            f"move one to another track")
    segs = sorted(plan.get("segs", []), key=lambda s: s[2])
    for x, y in zip(segs, segs[1:]):
        if y[2] != x[3]:
            errs.append(f"segs {x[2]}-{x[3]} and {y[2]}-{y[3]} {'overlap' if y[2] < x[3] else 'leave a gap'}")
    return errs

