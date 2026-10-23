"""Render a plan's HyperFrames overlays, place their sound cues, and build its CapCut draft (frame-exact,
integer-µs timing).

usage: python plan_build.py plan.json [--render-only] [--force]   (renders only missing overlays/cutouts; --force redoes all)
       python plan_build.py plan.json --snap-beats beats.json [--tol 3] [--music-at FRAME] [--tracks ui,flash] [--out f]
            move each overlay's start onto the nearest music beat (media_timing.py beats output) when one is
            within --tol frames, keeping its length; --music-at = the timeline frame where the music starts;
            only the listed --tracks move (default all); an overlay with "snap": false stays put (use it for
            overlays locked to a spoken word or a cut). Writes --out (default: plan.snapped.json) and lists moves.

Plan (frame numbers at 30 fps): see examples/cirelle_apple_ui_plan.json
  segs:     [file, src_in_seconds, from_frame, to_frame, scale]
  overlays: {template, from, to, track: ui|title|flash, vars, sfx: "default" | "none" | [{name, offset, len, volume}],
             cutout: true}  cutout = the speaker is cut out of the A-roll under this overlay and placed above it,
            so the graphic sits BEHIND the person (text behind you); the overlay must lie inside one seg
            sfx defaults per template: ../motion/sfx_defaults.json (files in ../motion/sfx/)
  music:    {file, volume}   optional bed under the voice, from frame 0 to the end
"""
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
MOTION = TOOLS.parent / "motion"
sys.path.insert(0, str(TOOLS))
import motion_render as mr  # noqa: E402
from machine import BUILD  # noqa: E402
from plan_common import US, SFX_TRACKS, MERGE_US, sfx_cues, beat_snap, check_plan  # noqa: E402,F401

API = "http://localhost:9001"



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
    for i, o in enumerate(plan["overlays"], 1):
        if not o.get("cutout"):
            continue
        file, src_t, scale = cutout_source(plan, o)
        o["cutout_file"], o["cutout_scale"] = str(mdir / f"{i:02d}_cutout.mov"), scale
        if force or not Path(o["cutout_file"]).exists():
            mr.cutout(Path(plan["clips_dir"] + file), Path(o["cutout_file"]), src_t, (US(o["to"]) - US(o["from"])) / 1e6)
            print(f"cutout   {i:02d} from {file} @ {src_t:.3f}s")


def cutout_source(plan: dict, o: dict) -> tuple[str, float, float]:
    """The A-roll seg under a cutout overlay: (file, source second at the overlay's start, seg scale)."""
    for file, src_in, a, b, scale in plan["segs"]:
        if a <= o["from"] and o["to"] <= b:
            return file, src_in + (US(o["from"]) - US(a)) / 1e6, scale
    raise ValueError(f"cutout overlay {o.get('template')} {o['from']}-{o['to']} must sit inside one seg")


def build(plan: dict) -> str:
    did = post("create_draft", {"width": 1080, "height": 1920})["output"]["draft_id"]
    end_us = 0
    # A-roll goes on "video", the default track create_draft makes: CapCut shows the bottom video track as
    # the main track, so a separate "video_main" would sit above an empty main track.
    for file, src_in, a, b, scale in plan["segs"]:
        s_us = round(src_in * 1e6)
        end_us = max(end_us, US(b))
        post("add_video", {"draft_id": did, "video_url": plan["clips_dir"] + file, "start": s_us / 1e6,
                           "end": (s_us + US(b) - US(a)) / 1e6, "target_start": US(a) / 1e6,
                           "track_name": "video", "relative_index": 0, "scale_x": scale, "scale_y": scale,
                           "volume": 1.0, "width": 1080, "height": 1920})
    for o in plan["overlays"]:
        post("add_video", {"draft_id": did, "video_url": o["file"], "start": 0,
                           "end": (US(o["to"]) - US(o["from"])) / 1e6, "target_start": US(o["from"]) / 1e6,
                           "track_name": f"overlay_{o['track']}", "relative_index": plan["tracks"][o["track"]],
                           "volume": 0, "width": 1080, "height": 1920})
    for o in plan["overlays"]:  # cutouts above every overlay, framed exactly like their A-roll seg
        if o.get("cutout_file"):
            post("add_video", {"draft_id": did, "video_url": o["cutout_file"], "start": 0,
                               "end": (US(o["to"]) - US(o["from"])) / 1e6, "target_start": US(o["from"]) / 1e6,
                               "track_name": "overlay_cutout", "relative_index": plan["tracks"].get("cutout", 8),
                               "scale_x": o["cutout_scale"], "scale_y": o["cutout_scale"], "volume": 0,
                               "width": 1080, "height": 1920})
    if plan.get("music"):
        post("add_audio", {"draft_id": did, "audio_url": plan["music"]["file"], "start": 0, "end": end_us / 1e6,
                           "target_start": 0, "volume": plan["music"].get("volume", 0.1), "track_name": "music"})
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
    errs = check_plan(plan)
    if errs:
        sys.exit("plan problems:\n- " + "\n- ".join(errs))
    render_overlays(plan, force="--force" in argv)  # only missing files, unless --force
    if "--render-only" in argv:
        return
    print(json.dumps({"draft": build(plan), "sfx_cues": len(sfx_cues(plan["overlays"]))}))


if __name__ == "__main__":
    main(sys.argv[1:])
