"""Render a plan's HyperFrames overlays, place their sound cues, and build its CapCut draft (frame-exact,
integer-µs timing).

usage: python plan_build.py plan.json [--render-only]

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

API = "http://localhost:9001"
BUILD = "C:/Users/Keytech/mcp-servers/tmp/build"
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
        for c in cues:
            cond = c.get("when")
            if cond:
                key, _, val = cond.partition("=")
                if str(vars_.get(key)) != val:
                    continue
            off = c.get("offset", 0)
            off = float(vars_.get(off, 0)) if isinstance(off, str) else float(off)
            at = US(o["from"]) + round(off * 1_000_000)
            ln = round(float(c.get("len", 0.6)) * 1_000_000)
            ov_end = US(o["to"])
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
    render_overlays(plan, force="--render-only" in argv)
    if "--render-only" in argv:
        return
    print(json.dumps({"draft": build(plan), "sfx_cues": len(sfx_cues(plan["overlays"]))}))


if __name__ == "__main__":
    main(sys.argv[1:])
