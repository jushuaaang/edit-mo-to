"""Build a whole CapCut project from the contract plan (plan_tools.py expand output) in one process.

CLI (prints JSON only):
    build <plan.json> [--import f ...] [--timelines "A,B"] [--job NAME] [--no-render]
        render every overlay (one parallel, deduped render_many call) and cutout, build one VectCutAPI draft
        per timeline, compose them into {capcut_drafts}/<plan.project>, import the plan's sources plus the
        --import files, snapshot each timeline to <base>/.edit-mo-to/built/<timeline>.json, write clip sheets
        to {tmp}/reports/<job>/sheets/ and the placed-clips table to {tmp}/reports/<job>/build_report.txt.
        Writes the rendered overlay "file" (and "cutout_file") paths back into plan.json, so sheets.py overlays
        and QA see the overlays, and the plan each timeline was built from (with those paths) to
        <base>/.edit-mo-to/built/<timeline>.plan.json: the old_plan of a later revise-in-place.
        --no-render uses each overlay's "file" as given (plan.json is then left as it is).
    timeline <plan.json> "<name>" [--as "<project timeline>"]
        build one timeline as a draft (for revise-new-timeline / revise-in-place); prints the draft folder and
        writes the built plan copy under the project timeline's name (--as, default <name>)
    mark-built <plan.json> "<name>" [--as "<project timeline>"]
        after a successful patch: the revised plan becomes the timeline's built plan copy; overlays without a
        "file" take it from the previous copy when template, vars, time, length and track are unchanged
    music <plan.json> "<name>" --music f --volume v [--end-s S]
        a music-only draft as long as that timeline, or S seconds (the captioned timeline's `segments`
        duration) (for add-tracks ... audio); prints the draft folder

Timing is whole frames at 30 fps, passed to VectCutAPI as integer microseconds / 1e6 (US(frame)).
"""
import json
import re
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import capcut_project as cp  # noqa: E402
import motion_render as mr  # noqa: E402
from machine import BUILD, PATHS, TMP  # noqa: E402
from media_timing import to_sf  # noqa: E402
from plan_common import US, clip_len_f, clip_volume, sfx_cues  # noqa: E402,F401  (SFX_TRACKS are the cue tracks sfx_cues assigns)

API = "http://localhost:9001"
TRACK_INDEX = {"video_main": 0, "video_top": 1, "video_bottom": 2, "video_overlay": 1}
OVERLAY_INDEX = {"ui": 5, "title": 6, "flash": 7}   # overlay roles -> layer, as editor.md places them
CUTOUT_INDEX = 8                                    # above every overlay
SPLIT_MASK = {"mask_type": "Rectangle", "mask_center_x": 0, "mask_center_y": 0, "mask_size": 0.5,
              "mask_rect_width": 1.0}
PATCH_HINT = "apply the VectCutAPI StopIteration patch (README, Manual setup step 5)"
# Windows: VectCutAPI prints Chinese log lines while applying keyframes at save; on a non-UTF-8 console that
# print raises and the whole save fails
KEYFRAME_HINT = ("This draft has keyframes: on Windows start VectCutAPI with PYTHONIOENCODING=utf-8, "
                 "or drop the keyframes and add them in CapCut.")


def post(ep: str, body: dict) -> dict:
    import requests

    r = requests.post(f"{API}/{ep}", json=body, timeout=180).json()
    if not r.get("success"):
        raise RuntimeError(f"{ep} failed: {r.get('error') or r} | body: {json.dumps(body, ensure_ascii=False)}")
    return r


def _f(seconds: float) -> int:
    """Contract seconds (10 decimals) -> whole frame."""
    return round(seconds * 30)


def _s(us: int) -> float:
    return us / 1e6


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_") or "tl"


def _canvas(plan: dict) -> tuple[int, int]:
    return int(plan.get("width", 1080)), int(plan.get("height", 1920))


def clip_frames(clip: dict) -> tuple[int, int]:
    """(at frame, timeline length in frames) of a clip; a sped clip keeps a whole-frame length."""
    return _f(clip["at"]), clip_len_f(clip)


def end_frame(timeline: dict) -> int:
    """The last clip's end; a timeline with no clips (an overlay-only draft) ends with its last overlay or text."""
    if timeline.get("clips"):
        return max(a + n for a, n in map(clip_frames, timeline["clips"]))
    rows = (timeline.get("overlays") or []) + (timeline.get("texts") or [])
    return max((_f(r["at"]) + _f(r["duration"]) for r in rows), default=0)


def overlays_to_frames(timeline: dict) -> list[dict]:
    """Contract overlays (seconds) -> {"template","from","to","vars","sfx","track"} in frames, the shape
    plan_common.sfx_cues reads. "file" and "cutout" are carried along when the overlay has them."""
    out = []
    for o in timeline.get("overlays", []):
        a = _f(o["at"])
        f = {"template": o["template"], "from": a, "to": a + _f(o["duration"]), "vars": o.get("vars", {}),
             "sfx": o.get("sfx", "none"), "track": o.get("track") or "ui"}
        for k in ("file", "cutout", "cutout_file"):
            if o.get(k):
                f[k] = o[k]
        out.append(f)
    return out


def clip_body(draft_id: str, clip: dict, canvas: tuple[int, int]) -> dict:
    """add_video body for one plan clip, integer-µs exact: the source span is start + the clip's whole-frame
    timeline length × speed, so back-to-back clips never overlap by a rounding µs."""
    at_f, len_f = clip_frames(clip)
    speed = clip.get("speed") or 1.0
    s_us = round(clip["src_in"] * 1e6)
    e_us = s_us + round((US(at_f + len_f) - US(at_f)) * speed)
    track = clip.get("track", "video_main")
    vol = clip_volume(clip)
    scale = clip.get("scale", 1.0)
    b = {"draft_id": draft_id, "video_url": clip["file"], "start": _s(s_us), "end": _s(e_us),
         "target_start": _s(US(at_f)), "track_name": "video" if track == "video_main" else track,
         "relative_index": TRACK_INDEX.get(track, 1), "width": canvas[0], "height": canvas[1], "speed": speed,
         "transform_x": clip.get("x", 0), "transform_y": clip.get("y", 0), "scale_x": scale, "scale_y": scale,
         "volume": vol}
    if clip.get("transition"):
        b["transition"] = clip["transition"]
        b["transition_duration"] = clip.get("transition_duration", 0.3)
    if clip.get("layout") in ("split-top", "split-bottom"):
        b.update(SPLIT_MASK)
    return b


def keyframe_body(draft_id: str, clip: dict, track_name: str) -> dict | None:
    """add_video_keyframe batch body: one (property, time, value) per entry, grouped by property, times in
    timeline seconds (clip at + t); the first point is nudged 1 ms in so it lands inside the clip."""
    kfs = clip.get("keyframes") or []
    if not kfs:
        return None
    times = [round(clip["at"] + k["t"], 6) for k in kfs]
    times[0] = round(times[0] + 0.001, 6)
    props = (("uniform_scale", "scale"), ("position_x", "x"), ("position_y", "y"))
    return {"draft_id": draft_id, "track_name": track_name,
            "property_types": [p for p, _ in props for _ in kfs],
            "times": [t for _ in props for t in times],
            "values": [str(float(k[key])) for _, key in props for k in kfs]}


def effect_body(draft_id: str, effect: dict) -> dict:
    a = _f(effect["at"])
    return {"draft_id": draft_id, "effect_type": effect["name"], "start": _s(US(a)),
            "end": _s(US(a + _f(effect["duration"]))), "params": [], "track_name": "effect_01"}


# editor.md's add_text presets (VectCutAPI's defaults are red Chinese-font text with no box)
TEXT_STYLES = {
    "badge": {"font_color": "#FFFFFF", "bold": True, "font_size": 10, "background_alpha": 1,
              "background_round_radius": 0.3, "transform_y": 0.6},
    "word": {"font_color": "#FFFFFF", "bold": True, "font_size": 14, "background_alpha": 0, "shadow_enabled": True,
             "transform_y": 0},
    "cta": {"font_color": "#FFFFFF", "bold": True, "font_size": 10, "background_alpha": 1,
            "background_round_radius": 0.3, "transform_y": -0.55},
}
TEXT_BG = "#E53935"   # badge / cta box when neither the text nor the brand gives a colour


def text_body(draft_id: str, text: dict, plan: dict) -> dict:
    """A contract text row -> add_text body styled by its preset; `bg` (else the brand accent) colours the box,
    `font` is passed only when the row gives one."""
    a = _f(text["at"])
    b = {"draft_id": draft_id, "text": text["text"], "start": _s(US(a)), "end": _s(US(a + _f(text["duration"]))),
         "track_name": "text_main", "width": _canvas(plan)[0], "height": _canvas(plan)[1],
         **TEXT_STYLES[text.get("style", "badge")]}
    if b["background_alpha"]:
        b["background_color"] = text.get("bg") or (plan.get("brand") or {}).get("accent") or TEXT_BG
    if text.get("font"):
        b["font"] = text["font"]
    return b


def vo_body(draft_id: str, timeline: dict, end_frame: int) -> dict:
    """The timeline's own VO span, ending on its last video frame (never the file length: CapCut rounds a
    partial frame up and leaves a black tail), and never past vo_out."""
    s_us = round(timeline["vo_in"] * 1e6)
    e_us = min(s_us + US(end_frame), round(timeline.get("vo_out", 1e9) * 1e6))
    return {"draft_id": draft_id, "audio_url": timeline["vo"], "start": _s(s_us), "end": _s(e_us),
            "target_start": 0, "volume": timeline.get("vo_volume", 1.0), "track_name": "vo"}


def _overlay_body(draft_id: str, o: dict, canvas: tuple[int, int]) -> dict:
    t = o["track"]
    return {"draft_id": draft_id, "video_url": o["file"], "start": 0, "end": _s(US(o["to"]) - US(o["from"])),
            "target_start": _s(US(o["from"])), "track_name": f"overlay_{t}" if t in OVERLAY_INDEX else t,
            "relative_index": OVERLAY_INDEX.get(t, OVERLAY_INDEX["ui"]), "volume": 0,
            "width": canvas[0], "height": canvas[1]}


def _cutout_clip(timeline: dict, o: dict) -> dict:
    """The main-track clip a cutout overlay sits on (the overlay must lie inside one clip)."""
    for c in timeline["clips"]:
        a, n = clip_frames(c)
        if c.get("track", "video_main") == "video_main" and a <= o["from"] and o["to"] <= a + n:
            return c
    raise ValueError(f"cutout overlay {o['template']} {o['from']}-{o['to']} must sit inside one main-track clip")


def _cutout_span(timeline: dict, o: dict) -> tuple[dict, float, float]:
    c = _cutout_clip(timeline, o)
    speed = c.get("speed") or 1.0
    src_t = c["src_in"] + (US(o["from"]) - US(_f(c["at"]))) / 1e6 * speed
    return c, src_t, (US(o["to"]) - US(o["from"])) / 1e6 * speed


def _motion_dir(plan: dict) -> Path:
    base = plan.get("base")
    return Path(base) / "motion" if base else TMP / "build" / "motion"


def _reusable(path: Path) -> bool:
    """An earlier render is reused only when it probes with alpha and a length (a crashed or half-written
    render is made again)."""
    if not Path(path).exists():
        return False
    try:
        info = mr._probe(Path(path))
    except Exception:  # noqa: BLE001
        return False
    return bool(info.get("alpha")) and (info.get("duration") or 0) > 0


def render_assets(plan: dict, timelines: list[dict], render_fn=mr.render) -> dict:
    """Render every overlay of these timelines that has no "file" in ONE render_many call (parallel, same
    template+vars+length rendered once), then their cutouts; writes "file" / "cutout_file" into the plan's
    overlay dicts. File names carry the job key, so an unchanged overlay is reused on a rerun (when it probes with
    alpha and a length)."""
    mdir = _motion_dir(plan)
    jobs, owners = [], []
    for tl in timelines:
        for n, (o, fr) in enumerate(zip(tl.get("overlays", []), overlays_to_frames(tl)), 1):
            if o.get("file"):
                continue
            v = {**o.get("vars", {}), "duration": (US(fr["to"]) - US(fr["from"])) / 1e6}
            out = mdir / f"{_slug(tl['name'])}_{n:02d}_{o['template']}_{mr.job_key(o['template'], v, v['duration'])[:8]}.mov"
            if _reusable(out):
                o["file"] = out.as_posix()
                continue
            jobs.append({"template": o["template"], "out": str(out), "vars": v})
            owners.append(o)
    results = mr.render_many(jobs, render_fn=render_fn) if jobs else []
    for o, r in zip(owners, results):
        o["file"] = Path(r["file"]).as_posix()
    cutouts = 0
    for tl in timelines:
        for n, (o, fr) in enumerate(zip(tl.get("overlays", []), overlays_to_frames(tl)), 1):
            if not o.get("cutout") or o.get("cutout_file"):
                continue
            c, src_t, length = _cutout_span(tl, fr)
            out = mdir / f"{_slug(tl['name'])}_{n:02d}_cutout_{mr.job_key('cutout', {'file': c['file']}, src_t)[:6]}_{fr['to'] - fr['from']}f.mov"
            if not _reusable(out):
                mr.cutout(Path(c["file"]), out, src_t, length)
                cutouts += 1
            o["cutout_file"] = out.as_posix()
    return {"rendered": len({r.get("copied_from") or r["file"] for r in results}), "jobs": len(jobs),
            "cutouts": cutouts}


def build_timeline(plan: dict, timeline: dict, post=post, render=True) -> dict:
    """One timeline -> one saved VectCutAPI draft. Order: create_draft, overlays (they create the overlay
    track before the second add_video, which sidesteps the one-video-track StopIteration bug), main-track
    clips, other video tracks, keyframes, effects, cutouts, texts, VO, music, SFX cues, save_draft, wait."""
    if render:
        render_assets(plan, [timeline])
    canvas = _canvas(plan)
    end_f = end_frame(timeline)
    frames = overlays_to_frames(timeline)
    missing = [o["template"] for o in frames if not o.get("file")]
    if missing:
        raise ValueError(f"{timeline['name']}: overlays without a rendered file: {missing}")
    did = post("create_draft", {"width": canvas[0], "height": canvas[1]})["output"]["draft_id"]
    counts = {"overlays": 0, "clips": 0, "keyframes": 0, "effects": 0, "cutouts": 0, "texts": 0, "vo": 0, "music": 0,
              "sfx": 0}
    for o in frames:
        post("add_video", _overlay_body(did, o, canvas))
        counts["overlays"] += 1
    clips = sorted(timeline.get("clips", []), key=lambda c: (c.get("track", "video_main") != "video_main",
                                                             TRACK_INDEX.get(c.get("track"), 1), c["at"]))
    for c in clips:
        post("add_video", clip_body(did, c, canvas))
        counts["clips"] += 1
    for c in clips:
        kb = keyframe_body(did, c, clip_body(did, c, canvas)["track_name"])
        if kb:
            post("add_video_keyframe", kb)
            counts["keyframes"] += len(c["keyframes"])
    # a clip's own `effect` runs over that clip's span
    clip_fx = [{"name": c["effect"], "at": c["at"], "duration": clip_frames(c)[1] / 30} for c in clips if c.get("effect")]
    for e in (timeline.get("effects", []) or []) + clip_fx:
        post("add_effect", effect_body(did, e))
        counts["effects"] += 1
    for o in frames:
        if not o.get("cutout"):
            continue
        if not o.get("cutout_file"):
            raise ValueError(f"{timeline['name']}: cutout overlay {o['template']} at {o['from']} has no cutout file")
        c, _, length = _cutout_span(timeline, o)
        cb = clip_body(did, c, canvas)
        post("add_video", {"draft_id": did, "video_url": o["cutout_file"], "start": 0, "end": length,
                           "target_start": _s(US(o["from"])), "track_name": "overlay_cutout",
                           "relative_index": CUTOUT_INDEX, "speed": cb["speed"], "scale_x": cb["scale_x"],
                           "scale_y": cb["scale_y"], "transform_x": cb["transform_x"],
                           "transform_y": cb["transform_y"], "volume": 0, "width": canvas[0], "height": canvas[1]})
        counts["cutouts"] += 1
    for t in timeline.get("texts", []) or []:
        post("add_text", text_body(did, t, plan))
        counts["texts"] += 1
    if timeline.get("vo"):
        post("add_audio", vo_body(did, timeline, end_f))
        counts["vo"] = 1
    if timeline.get("music"):
        post("add_audio", {"draft_id": did, "audio_url": timeline["music"], "start": 0, "end": _s(US(end_f)),
                           "target_start": 0, "volume": timeline.get("music_volume", 0.1), "track_name": "music"})
        counts["music"] = 1
    # no clips: nothing to cut the cues at (an overlay-only draft merged into a built timeline keeps every cue)
    for cue in sfx_cues(frames, US(end_f) if timeline.get("clips") else None):
        post("add_audio", {"draft_id": did, "audio_url": cue["file"], "start": 0, "end": _s(cue["len_us"]),
                           "target_start": _s(cue["at_us"]), "volume": cue["volume"], "track_name": cue["track"]})
        counts["sfx"] += 1
    _save(did, post, hint=KEYFRAME_HINT if counts["keyframes"] else "")
    draft = cp.wait_for_draft(Path(BUILD) / did)
    return {"draft": str(draft), "end_frame": end_f, "counts": counts}


def _save(did: str, post, hint: str = "") -> None:
    """save_draft; VectCutAPI answers success with an empty draft_url when the save itself crashed
    (it then leaves an empty draft behind), so that counts as a failure."""
    out = post("save_draft", {"draft_id": did, "draft_folder": BUILD, "auto_deploy": False}).get("output")
    if isinstance(out, dict) and "draft_url" in out and not out["draft_url"]:
        raise cp.DraftSaveFailed(f"save_draft of {did} failed inside VectCutAPI (empty draft_url). {hint}".strip())


def stop_iteration_patched(path: Path | None = None) -> bool:
    """True when VectCutAPI's add_video_track.py carries the local StopIteration patch
    (same test as `grep -c "StopIteration" {mcp_servers}/VectCutAPI/add_video_track.py` > 0)."""
    path = Path(path or Path(PATHS["mcp_servers"]) / "VectCutAPI" / "add_video_track.py")
    try:
        return sum("StopIteration" in ln for ln in path.read_text(encoding="utf-8", errors="ignore").splitlines()) > 0
    except OSError:
        return False


def _pick(plan: dict, timelines) -> list[dict]:
    if not timelines:
        return list(plan["timelines"])
    by_name = {t["name"]: t for t in plan["timelines"]}
    unknown = [n for n in timelines if n not in by_name]
    if unknown:
        raise ValueError(f"unknown timeline(s) {unknown}; plan has {list(by_name)}")
    return [by_name[n] for n in timelines]


def _sources(timelines: list[dict]) -> list[str]:
    out = []
    for tl in timelines:
        for f in [c["file"] for c in tl.get("clips", [])] + [tl.get("vo"), tl.get("music")]:
            if f and f not in out:
                out.append(f)
    return out


def report_table(timelines: list[dict]) -> str:
    rows = ["Timeline | # | File | At (s:ff) | Len | Notes"]
    for tl in timelines:
        for n, c in enumerate(sorted(tl.get("clips", []), key=lambda c: c["at"]), 1):
            a, ln = clip_frames(c)
            notes = [c.get("layout") or c.get("track", "video_main")]
            if (c.get("speed") or 1.0) != 1.0:
                notes.append(f"speed {c['speed']}")
            if c.get("transition"):
                notes.append(c["transition"])
            if c.get("keyframes"):
                notes.append(f"{len(c['keyframes'])} keyframes")
            if not c.get("mute", True):
                notes.append(f"audio {c.get('gain_db', 0):+g} dB")
            rows.append(f"{tl['name']} | {n} | {c['file']} | {to_sf(a / 30)} | {to_sf(ln / 30)} | {', '.join(notes)}")
    return "\n".join(rows) + "\n"


def save_plan(plan: dict, path: Path) -> None:
    """Write the plan back (temp file + replace, so a crash never leaves half a plan.json)."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(plan, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def built_plan_path(base: Path, name: str) -> Path:
    """Where the plan a timeline was last built or patched from lives (next to its edit_diff snapshot)."""
    return Path(base) / ".edit-mo-to" / "built" / f"{name}.plan.json"


def _base(plan: dict, job=None) -> Path:
    return Path(plan["base"]) if plan.get("base") else TMP / "reports" / (job or _slug(plan.get("project", "job")))


def save_built(plan: dict, tl: dict, name: str | None = None, job=None) -> Path:
    """The plan with only this timeline (renamed to the project timeline `name`), atomically."""
    name = name or tl["name"]
    one = {**{k: v for k, v in plan.items() if k != "timelines"}, "timelines": [{**tl, "name": name}]}
    path = built_plan_path(_base(plan, job), name)
    path.parent.mkdir(parents=True, exist_ok=True)
    save_plan(one, path)
    return path


OVERLAY_KEY = ("template", "vars", "at", "duration", "track", "cutout")


def mark_built(plan: dict, name: str, as_name: str | None = None) -> dict:
    """After a patch: the revised plan's timeline becomes the built copy. Overlays the revision left unchanged
    keep the rendered file of the previous copy; changed ones without a file are listed as unrendered."""
    as_name = as_name or name
    tl = json.loads(json.dumps(_pick(plan, [name])[0]))
    old_p = built_plan_path(_base(plan), as_name)
    old = json.loads(old_p.read_text(encoding="utf-8"))["timelines"][0].get("overlays", []) if old_p.exists() else []
    carried, unrendered = 0, []
    for n, o in enumerate(tl.get("overlays", []), 1):
        if o.get("file"):
            continue
        prev = next((x for x in old if x.get("file") and all(x.get(k) == o.get(k) for k in OVERLAY_KEY)), None)
        if prev:
            o["file"] = prev["file"]
            if prev.get("cutout_file"):
                o["cutout_file"] = prev["cutout_file"]
            carried += 1
        else:
            unrendered.append(f"ov{n} {o.get('template', '')}")
    return {"built_plan": str(save_built(plan, tl, as_name)), "carried": carried, "unrendered": unrendered}


def build(plan: dict, import_files=(), timelines=None, job=None, post=post, render=True, plan_path=None) -> dict:
    """The whole project: overlays rendered once for all timelines, one draft per timeline, compose, import,
    snapshots, clip and overlay sheets and the report. With `plan_path`, the plan (now carrying each overlay's
    rendered "file") is written back there. Returns the short summary (≤ 25 lines as printed)."""
    import sheets

    tls = _pick(plan, timelines)
    if any(not tl.get("overlays") for tl in tls) and not stop_iteration_patched():
        raise RuntimeError(PATCH_HINT)
    job = job or _slug(plan.get("project", "job"))
    reports = TMP / "reports" / job
    reports.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    rendered = render_assets(plan, tls) if render else {"rendered": 0, "jobs": 0, "cutouts": 0}
    t_render = time.time() - t0
    if plan_path and render:   # --no-render changed nothing in the plan
        save_plan(plan, plan_path)
    built = [(tl["name"], build_timeline(plan, tl, post=post, render=False)) for tl in tls]
    project = Path(PATHS["capcut_drafts"]) / plan["project"]
    comp = cp.compose(project, [(n, Path(b["draft"])) for n, b in built], link_originals=True)
    imported = cp.import_media(project, _sources(tls) + [str(f) for f in import_files])
    failures, sheet_paths = [], []
    base = Path(plan["base"]) if plan.get("base") else reports
    for tl in tls:
        try:  # the edit_diff snapshot: capcut_project.segments written as JSON
            snap = base / ".edit-mo-to" / "built" / f"{tl['name']}.json"
            snap.parent.mkdir(parents=True, exist_ok=True)
            snap.write_text(json.dumps(cp.segments(project, tl["name"], [base]), ensure_ascii=False), encoding="utf-8")
        except Exception as e:  # noqa: BLE001  (a missing snapshot only weakens the learning step)
            failures.append(f"snapshot {tl['name']}: {e}")
        try:
            save_built(plan, tl, job=job)
        except OSError as e:
            failures.append(f"built plan {tl['name']}: {e}")
        try:
            sheet_paths += [s["path"] for s in sheets.clip_sheets(plan, tl["name"], reports / "sheets")["sheets"]]
            if tl.get("overlays"):
                sheet_paths += [s["path"] for s in sheets.overlay_sheets(plan, tl["name"], reports / "sheets")["sheets"]]
        except Exception as e:  # noqa: BLE001
            failures.append(f"sheets {tl['name']}: {e}")
    report = reports / "build_report.txt"
    report.write_text(report_table(tls), encoding="utf-8")
    manual = [m for tl in tls for m in tl.get("manual", [])]
    if plan.get("fps", 30) != 30:
        manual.append(f"set project frame rate to {plan['fps']}")
    manual += [f"check {f} isn't sideways" for f in comp.get("rotation_unchecked", [])]
    failures += [f"import: missing {f}" for f in imported["missing"]]
    counts = {k: sum(b["counts"][k] for _, b in built) for k in built[0][1]["counts"]} if built else {}
    return {"project": comp["project"], "timelines": comp["timelines"],
            "end_frames": {n: b["end_frame"] for n, b in built}, "counts": counts,
            "rendered": rendered, "render_s": round(t_render, 1), "total_s": round(time.time() - t0, 1),
            "imported": len(imported["added"]), "rotation_fixed": len(comp.get("rotation_fixed", [])),
            "sheets": sheet_paths, "report": str(report), "failures": failures, "manual": manual}


def timeline(plan: dict, name: str, post=post, as_name: str | None = None) -> str:
    """One timeline as a draft (renders its missing overlays first), plus its built plan copy under the
    project timeline's name; returns the draft folder."""
    tl = _pick(plan, [name])[0]
    draft = build_timeline(plan, tl, post=post)["draft"]
    save_built(plan, tl, as_name or name)
    return draft


def music_draft(end_frame: int, music: str, volume: float, post=post, canvas=(1080, 1920)) -> str:
    """A draft holding only the music bed, end_frame long, for add-tracks ... audio."""
    did = post("create_draft", {"width": canvas[0], "height": canvas[1]})["output"]["draft_id"]
    post("add_audio", {"draft_id": did, "audio_url": music, "start": 0, "end": _s(US(end_frame)), "target_start": 0,
                       "volume": volume, "track_name": "music"})
    _save(did, post)
    return str(cp.wait_for_draft(Path(BUILD) / did))


def _dump_short(d: dict) -> str:
    """One top-level key per line: valid JSON that stays within the 25-line summary."""
    return "{\n" + ",\n".join(f" {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in d.items()) + "\n}"


def main(argv: list[str]) -> None:
    if len(argv) < 2:
        raise SystemExit(__doc__)
    cmd, plan_path, rest = argv[0], Path(argv[1]), argv[2:]
    plan = json.loads(plan_path.read_text(encoding="utf-8"))

    def opt(k, d=None):
        return rest[rest.index(k) + 1] if k in rest else d

    if cmd == "build":
        imports, i = [], 0
        while i < len(rest):
            if rest[i] == "--import":
                i += 1
                while i < len(rest) and not rest[i].startswith("--"):
                    imports.append(rest[i])
                    i += 1
            else:
                i += 1
        tls = [t.strip() for t in opt("--timelines", "").split(",") if t.strip()] or None
        print(_dump_short(build(plan, imports, tls, opt("--job"), render="--no-render" not in rest,
                                plan_path=plan_path)))
    elif cmd == "timeline" and rest:
        print(json.dumps({"draft": timeline(plan, rest[0], as_name=opt("--as"))}, ensure_ascii=False))
    elif cmd == "mark-built" and rest:
        print(json.dumps(mark_built(plan, rest[0], opt("--as")), ensure_ascii=False))
    elif cmd == "music" and rest and opt("--music"):
        tl = _pick(plan, [rest[0]])[0]
        # --end-s: the captioned timeline's real length (capcut_project.py segments `duration`), when hand edits
        # made it differ from the plan's
        end_f = round(float(opt("--end-s")) * 30) if opt("--end-s") else end_frame(tl)
        print(json.dumps({"draft": music_draft(end_f, opt("--music"), float(opt("--volume", 0.1)),
                                               canvas=_canvas(plan))}, ensure_ascii=False))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1:])
