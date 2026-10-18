"""Render a plan's HyperFrames overlays, place their sound cues, and build its CapCut draft (frame-exact,
integer-µs timing).

usage: python plan_build.py plan.json [--render-only]
       python plan_build.py plan.json --snap-beats beats.json [--tol 3] [--music-at FRAME] [--tracks ui,flash] [--out f]
            move each overlay's start onto the nearest music beat (media_timing.py beats output) when one is
            within --tol frames, keeping its length; --music-at = the timeline frame where the music starts;
            only the listed --tracks move (default all); an overlay with "snap": false stays put (use it for
            overlays locked to a spoken word or a cut). Writes --out (default: plan.snapped.json) and lists moves.

Plan (frame numbers at 30 fps): see examples/cirelle_apple_ui_plan.json
  segs:     [file, src_in_seconds, from_frame, to_frame, scale]
  overlays: {template, from, to, track: ui|title|flash, vars, sfx: "default" | "none" | [{name, offset, len, volume}]}
            sfx defaults per template: ../motion/sfx_defaults.json (files in ../motion/sfx/)
"""
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
MOTION = TOOLS.parent / "motion"
sys.path.insert(0, str(TOOLS))
import motion_render as mr  # noqa: E402
from machine import BUILD  # noqa: E402

API = "http://localhost:9001"
SFX_TRACKS = ("sfx_a", "sfx_b", "sfx_c")
MERGE_US = 150_000


def US(frame: int) -> int:
    """Frame (30 fps) -> whole microseconds, the unit VectCutAPI stores."""
    return round(frame * 1_000_000 / 30)


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


def post(ep, body):
    import requests

    r = requests.post(f"{API}/{ep}", json=body, timeout=180).json()
    if not r.get("success"):
        sys.exit(f"{ep} failed at {body.get('target_start')} {body.get('track_name')}: {r}")
    return r


def render_overlays(plan: dict, force: bool = False) -> None:
    mdir = Path(plan["motion_dir"])
    mdir.mkdir(parents=True, exist_ok=True)
    for i, o in enumerate(plan["overlays"], 1):
        o["file"] = str(mdir / f"{i:02d}_{o['template']}.mov")
        dur = (US(o["to"]) - US(o["from"])) / 1e6
        if not force and Path(o["file"]).exists():
            continue
        info = mr.render(o["template"], Path(o["file"]), {**o["vars"], "duration": dur})
        print(f"rendered {i:02d} {o['template']:14s} {dur:.3f}s alpha={info['alpha']}")


def build(plan: dict) -> str:
    did = post("create_draft", {"width": 1080, "height": 1920})["output"]["draft_id"]
    end_us = 0
    for file, src_in, a, b, scale in plan["segs"]:
        s_us = round(src_in * 1e6)
        end_us = max(end_us, US(b))
        post("add_video", {"draft_id": did, "video_url": plan["clips_dir"] + file, "start": s_us / 1e6,
                           "end": (s_us + US(b) - US(a)) / 1e6, "target_start": US(a) / 1e6,
                           "track_name": "video_main", "relative_index": 0, "scale_x": scale, "scale_y": scale,
                           "volume": 1.0, "width": 1080, "height": 1920})
    for o in plan["overlays"]:
        post("add_video", {"draft_id": did, "video_url": o["file"], "start": 0,
                           "end": (US(o["to"]) - US(o["from"])) / 1e6, "target_start": US(o["from"]) / 1e6,
                           "track_name": f"overlay_{o['track']}", "relative_index": plan["tracks"][o["track"]],
                           "volume": 0, "width": 1080, "height": 1920})
    for c in sfx_cues(plan["overlays"], end_us):
        post("add_audio", {"draft_id": did, "audio_url": c["file"], "start": 0, "end": c["len_us"] / 1e6,
                           "target_start": c["at_us"] / 1e6, "volume": c["volume"], "track_name": c["track"]})
    post("save_draft", {"draft_id": did, "draft_folder": BUILD, "auto_deploy": False})
    return f"{BUILD}/{did}"


def main(argv: list[str]) -> None:
    if not argv:
        raise SystemExit(__doc__)
    plan = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    if "--snap-beats" in argv:
        opt = lambda k, d: argv[argv.index(k) + 1] if k in argv else d
        beats = json.loads(Path(opt("--snap-beats", "")).read_text(encoding="utf-8"))
        moves = beat_snap(plan["overlays"], beats["beats"] if isinstance(beats, dict) else beats,
                          int(opt("--tol", 3)), int(opt("--music-at", 0)),
                          [t for t in opt("--tracks", "").split(",") if t] or None)
        out = Path(opt("--out", str(Path(argv[0]).with_suffix(".snapped.json"))))
        out.write_text(json.dumps(plan, indent=1, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({"plan": str(out), "moved": moves}, ensure_ascii=False))
        return
    render_overlays(plan, force="--render-only" in argv)
    if "--render-only" in argv:
        return
    print(json.dumps({"draft": build(plan), "sfx_cues": len(sfx_cues(plan["overlays"]))}))


if __name__ == "__main__":
    main(sys.argv[1:])
