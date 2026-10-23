"""Compact frame plan -> contract plan, plus the plan table.

CLI (prints JSON):
    expand <plan2.json> [--out plan.json] [--table plan_table.txt]
                         expand the compact frame plan (plan2) into the edit-plan JSON the editor builds from
    check <plan.json> [--limits limits.json]
                         timing, reuse, VO edges, overlay, template and scale problems; exit code 1 when any
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import motion_render as mr  # noqa: E402
from machine import TMP  # noqa: E402
from media_timing import to_sf  # noqa: E402

TRACKS = {"main": "video_main", "top": "video_top", "bottom": "video_bottom", "overlay": "video_overlay"}
BRAND_KEYS = ("font", "bg", "fg", "accent")
CLIP_DERIVED = {"track", "speed", "mute", "kf", "transition_f"}  # opts that are converted, not copied as given


def sec(frame: int) -> float:
    return round(frame / 30, 10)


def _frame(value, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{what} must be a whole frame, got {value!r}")
    return value


def _join(base: str, file: str) -> str:
    if file.startswith("/") or re.match(r"^[A-Za-z]:[\/]", file):
        return file
    return base.rstrip("/") + "/" + file


def _clip(row: list, shift: int, base: str, block: str | None, where: str) -> dict:
    if len(row) < 4:
        raise ValueError(f"{where}: clip row needs [file, src_in_f, at_f, len_f, opts?]")
    file, src_in_f, at_f, len_f = row[:4]
    opts = row[4] if len(row) > 4 else {}
    src_in_f, at_f, len_f = (_frame(v, f"{where} {n}") for v, n in
                             ((src_in_f, "src_in_f"), (at_f, "at_f"), (len_f, "len_f")))
    at_f += shift
    track = opts.get("track", "main")
    if track not in TRACKS:
        raise ValueError(f"{where}: unknown track {track!r}; use {sorted(TRACKS)}")
    speed = float(opts.get("speed", 1.0))
    c = {"file": _join(base, file), "src_in": sec(src_in_f), "src_out": sec(round(src_in_f + len_f * speed)),
         "at": sec(at_f), "speed": speed, "track": TRACKS[track], "x": 0.0, "y": 0.0, "scale": 1.0,
         "transition": None, "effect": None, "mute": opts.get("mute", True)}
    c.update({k: v for k, v in opts.items() if k not in CLIP_DERIVED})
    if c["transition"]:
        c["transition_duration"] = sec(_frame(opts.get("transition_f", 9), f"{where} transition_f"))
    if "kf" in opts:
        c["keyframes"] = [{"t": sec(_frame(t, f"{where} kf t_f")), "scale": s, "x": x, "y": y}
                          for t, s, x, y in opts["kf"]]
    if block:
        c["block"] = block
    c["_end_f"] = at_f + len_f
    return c


def _overlay(row: list, shift: int, brand: dict, block: str | None, where: str) -> dict:
    if len(row) < 6:
        raise ValueError(f"{where}: overlay row needs [template, at_f, len_f, vars, track, sfx, opts?]")
    template, at_f, len_f, variables, track, sfx = row[:6]
    opts = row[6] if len(row) > 6 else {}
    at_f, len_f = _frame(at_f, f"{where} at_f"), _frame(len_f, f"{where} len_f")
    declared = mr.list_templates().get(template, {}).get("defaults", {})
    v = dict(variables)
    for k in BRAND_KEYS:
        if k in brand and k in declared and k not in v:
            v[k] = brand[k]
    o = {"template": template, "vars": v, "at": sec(at_f + shift), "duration": sec(len_f),
         "track": track, "sfx": sfx, **opts}
    if block:
        o["block"] = block
    return o


def _effect(row: list, shift: int, where: str) -> dict:
    name, at_f, len_f = row
    return {"name": name, "at": sec(_frame(at_f, f"{where} at_f") + shift),
            "duration": sec(_frame(len_f, f"{where} len_f"))}


def _timeline(tl: dict, plan2: dict) -> dict:
    base, brand, blocks = plan2.get("base", ""), plan2.get("brand", {}), plan2.get("blocks", {})
    name = tl["name"]
    clips, overlays, effects = [], [], []
    for n, item in enumerate(tl.get("seq", []), 1):
        shift = _frame(item.get("at_f", 0), f"{name} seq {n} at_f")
        block = item.get("use")
        if block is not None:
            if block not in blocks:
                raise ValueError(f"{name}: unknown block {block!r}; have {sorted(blocks)}")
            body = blocks[block]
        else:
            body = item
        where = f"{name} seq {n}" + (f" ({block})" if block else "")
        clips += [_clip(r, shift, base, block, where) for r in body.get("clips", [])]
        overlays += [_overlay(r, shift, brand, block, where) for r in body.get("overlays", [])]
        effects += [_effect(r, shift, where) for r in body.get("effects", [])]
    end_f = max((c["_end_f"] for c in clips), default=0)
    for c in clips:
        del c["_end_f"]
    vo, music = plan2.get("vo"), plan2.get("music")
    out = {"name": name,
           "vo": _join(base, vo["file"]) if vo else None,
           "vo_in": sec(_frame(tl.get("vo_in_f", 0), f"{name} vo_in_f")),
           "vo_out": sec(_frame(tl.get("vo_out_f", end_f), f"{name} vo_out_f")),
           "vo_volume": vo.get("volume", 1.0) if vo else 1.0,
           "music": _join(base, music["file"]) if music else None,
           "music_volume": music.get("volume", 0.1) if music else 0.1,
           "clips": clips, "overlays": overlays, "texts": [], "manual": tl.get("manual", [])}
    if effects:
        out["effects"] = effects
    return out


def expand(plan2: dict) -> dict:
    """Compact frame plan (plan2) -> contract plan: frames become 10-decimal seconds, blocks are resolved,
    brand vars are filled into the overlays whose template declares them."""
    plan = {k: plan2[k] for k in ("project", "fps", "width", "height", "base", "brand") if k in plan2}
    plan["timelines"] = [_timeline(tl, plan2) for tl in plan2.get("timelines", [])]
    return plan


def plan_table(plan: dict) -> str:
    rows = ["# | Timeline | At | Len | File | Src in–out | Speed | Layout | Transition/Effect | Line"]
    n = 0
    for tl in plan["timelines"]:
        for c in tl["clips"]:
            n += 1
            ln = round((c["src_out"] - c["src_in"]) * 30 / c["speed"]) / 30
            fx = " ".join(str(x) for x in (c.get("transition"), c.get("effect")) if x)
            rows.append(" | ".join([str(n), tl["name"], to_sf(c["at"]), to_sf(ln), c["file"],
                                    f"{to_sf(c['src_in'])}–{to_sf(c['src_out'])}", f"{c['speed']:g}x",
                                    str(c.get("layout") or c["track"]), fx, str(c.get("line", ""))]))
    return "\n".join(rows)


CANVAS = (1080, 1920)
BAND_OK = {"cta", "end-card", "title-card"}   # templates that belong in the caption band
SPLIT_TRACKS = {"video_top", "video_bottom"}  # sized by their layout, not by the full-frame scale rule
EPS = 1e-6


def probe_media(path: str) -> dict:
    """{"duration", "width", "height", "fps", "rotation"} of a media file by ffprobe, cached as JSON in
    {tmp}/probe/<sha1 of path|size|mtime>.json."""
    st = Path(path).stat()
    cache = TMP / "probe" / (hashlib.sha1(f"{path}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest() + ".json")
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "stream=codec_type,width,height,r_frame_rate:stream_side_data=rotation:format=duration",
                        "-of", "json", path], capture_output=True, text=True)
    d = json.loads(r.stdout or "{}")
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
    num, _, den = str(v.get("r_frame_rate", "0/1")).partition("/")
    rot = next((sd["rotation"] for sd in v.get("side_data_list", []) if "rotation" in sd), 0)
    out = {"duration": float((d.get("format") or {}).get("duration") or 0), "width": v.get("width"),
           "height": v.get("height"), "fps": round(float(num) / float(den or 1), 3) if v else None,
           "rotation": int(rot)}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out), encoding="utf-8")
    return out


def edge_silent(path: str, t: float, window: float = 0.8, floor_db: float = -60.0) -> bool:
    """True when the audio around t is below floor_db: RMS in 20 ms steps over a window starting 0.3 s before t
    (the probe qa.md prescribes; Whisper word ends run about 0.25 s early, so levels decide)."""
    r = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-ss", f"{max(t - 0.3, 0):.3f}", "-t", f"{window}",
                        "-i", path, "-af", "asetnsamples=n=882,astats=metadata=1:reset=1,"
                        "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-", "-f", "null", "-"],
                       capture_output=True, text=True)
    levels = [-200.0 if "inf" in m else float(m) for m in re.findall(r"RMS_level=(-?inf|-?[\d.]+)", r.stdout)]
    return bool(levels) and max(levels) < floor_db


def source_overlaps(a: dict, b: dict) -> bool:
    """Two clips use the same file and overlapping stretches of it."""
    return a["file"] == b["file"] and a["src_in"] < b["src_out"] - EPS and b["src_in"] < a["src_out"] - EPS


def _whole(x: float) -> bool:
    return abs(x * 30 - round(x * 30)) < 1e-3


def _clip_len(c: dict) -> float:
    return (c["src_out"] - c["src_in"]) / c.get("speed", 1.0)


def _scale_errors(c: dict, info: dict, where: str) -> list[str]:
    errs = []
    scale = c.get("scale", 1.0)
    if scale > 2.0 and not c.get("allow_scale"):
        errs.append(f"{where}: scale {scale} is above 2.0; set allow_scale if the punch-in is meant")
    w, h = info.get("width"), info.get("height")
    if w and h and c.get("track") not in SPLIT_TRACKS:
        if abs(info.get("rotation", 0)) % 180 == 90:
            w, h = h, w
        f = min(CANVAS[0] / w, CANVAS[1] / h)
        if scale * w * f < CANVAS[0] * 0.99 or scale * h * f < CANVAS[1] * 0.99:   # 1% slack: 320x568 is "9:16"
            errs.append(f"{where}: scale {scale} leaves black edges on a {w}x{h} source "
                        f"(fitted {round(w * f)}x{round(h * f)} in a {CANVAS[0]}x{CANVAS[1]} canvas); "
                        f"use scale >= {max(CANVAS[0] / (w * f), CANVAS[1] / (h * f)):.2f}")
    return errs


def _overlay_errors(o: dict, n: int, cuts: list[float], tl: str, templates: dict, limits: dict) -> list[str]:
    where, errs, name = f"{tl} overlay {n}", [], o["template"]
    if name not in templates:
        errs.append(f"{where}: no template '{name}'; have {sorted(templates)}")
    else:
        defaults = templates[name]["defaults"]
        try:
            v = dict(o.get("vars", {}))
            if "duration" in defaults:
                v.setdefault("duration", o["duration"])
            mr.fill(mr.template_text(name), v)
        except Exception as e:  # unknown var name, bad duration, ...
            errs.append(f"{where}: template '{name}' rejects its vars: {e}")
        vars_ = o.get("vars", {})
        top = vars_.get("top", vars_.get("y", defaults.get("top", defaults.get("y"))))
        band = limits.get("caption_band_px", 400)
        try:
            in_band = top is not None and float(top) >= CANVAS[1] - band
        except (TypeError, ValueError):
            in_band = False
        if in_band and name not in BAND_OK:
            errs.append(f"{where}: '{name}' sits at y {top}, inside the bottom {band} px caption band "
                        f"(only {sorted(BAND_OK)} may)")
    if o.get("on") not in ("word", "beat") and not any(abs(o["at"] - c) <= 1 / 30 + EPS for c in cuts):
        errs.append(f"{where}: starts at {o['at']} and does not start on a cut; move it to a clip start "
                    f"or set \"on\": \"word\" / \"beat\"")
    sfx = o.get("sfx", "none")
    if isinstance(sfx, list):
        for c in sfx:
            if not (mr.TEMPLATES.parent / "sfx" / f"{c.get('name')}.mp3").exists():
                errs.append(f"{where}: sfx '{c.get('name')}' not found in motion/sfx/")
    return errs


def check(plan: dict, limits: dict | None = None, probe=probe_media, silent=edge_silent) -> list[str]:
    """Everything the editor or QA would trip over, found on the contract plan before either runs.
    Each error starts with `T<n> clip <m>:`, `T<n> overlay <m>:` or `T<n> vo:` (1-based)."""
    limits, errs, info = limits or {}, [], {}
    templates = mr.list_templates()

    def media(path):
        if path not in info:
            try:
                info[path] = probe(path)
            except Exception as e:
                info[path] = e
        return info[path]

    seen = []   # (timeline label, clip number, clip) of every clip so far, for reuse checks
    for ti, tl in enumerate(plan.get("timelines", []), 1):
        T = f"T{ti}"
        clips = tl.get("clips", [])
        for ci, c in enumerate(clips, 1):
            where = f"{T} clip {ci}"
            for k in ("at", "src_in", "src_out"):
                if not _whole(c[k]):
                    errs.append(f"{where}: {k} {c[k]} is not a whole frame at 30 fps")
            if not _whole(_clip_len(c)):
                errs.append(f"{where}: length {round(_clip_len(c), 4)} s is not a whole frame at 30 fps")
            m = media(c["file"])
            if isinstance(m, Exception):
                errs.append(f"{where}: cannot read {c['file']}: {m}")
            else:
                if c["src_out"] > m["duration"] + 1 / 30 + EPS:
                    errs.append(f"{where}: src_out {c['src_out']} is past the file end {m['duration']} ({c['file']})")
                errs += _scale_errors(c, m, where)
            for lt, cj, other in seen:
                if not source_overlaps(c, other):
                    continue
                if lt == T:
                    errs.append(f"{where}: source reused from {T} clip {cj} ({c['file']} {c['src_in']}-{c['src_out']})")
                elif not any(x.get("block") or x.get("shared") for x in (c, other)):
                    errs.append(f"{where}: source overlaps {lt} clip {cj} ({c['file']} {c['src_in']}-{c['src_out']}); "
                                f"use another take or mark it shared")
            seen.append((T, ci, c))
        main = sorted(((c, i) for i, c in enumerate(clips, 1) if c.get("track") == "video_main"), key=lambda x: x[0]["at"])
        for (a, _), (b, bi) in zip(main, main[1:]):
            end = a["at"] + _clip_len(a)
            if b["at"] > end + EPS:
                errs.append(f"{T} clip {bi}: gap on the main track; the previous clip ends at {round(end, 4)}, "
                            f"this one starts at {b['at']}")
            elif b["at"] < end - EPS:
                errs.append(f"{T} clip {bi}: overlaps the previous main-track clip (it ends {round(end, 4)}, "
                            f"this one starts {b['at']})")
        end_s = max((c["at"] + _clip_len(c) for c in clips), default=0.0)
        if limits.get("min_s") and end_s < limits["min_s"] - EPS:
            errs.append(f"{T} vo: timeline ends at {round(end_s, 3)} s, below the minimum {limits['min_s']} s")
        if limits.get("max_s") and end_s > limits["max_s"] + EPS:
            errs.append(f"{T} vo: timeline ends at {round(end_s, 3)} s, above the maximum {limits['max_s']} s")
        if tl.get("vo"):
            m = media(tl["vo"])
            if isinstance(m, Exception):
                errs.append(f"{T} vo: cannot read {tl['vo']}: {m}")
            else:
                if tl["vo_out"] > m["duration"] + 1 / 30 + EPS:
                    errs.append(f"{T} vo: vo_out {tl['vo_out']} is past the file end {m['duration']}")
                edges = [("vo_in", tl["vo_in"])] if tl["vo_in"] > 0 else []
                if tl["vo_out"] < m["duration"] - EPS:
                    edges.append(("vo_out", tl["vo_out"]))
                for label, t in edges:
                    if not silent(tl["vo"], t):
                        errs.append(f"{T} vo: {label} {t} is not silent (above -60 dB within the 0.8 s probe); "
                                    f"move it into the gap between words")
        cuts, by_track = [c["at"] for c in clips], {}
        for oi, o in enumerate(tl.get("overlays", []), 1):
            errs += _overlay_errors(o, oi, cuts, T, templates, limits)
            by_track.setdefault(o["track"], []).append((o["at"], o["at"] + o["duration"], oi))
        for track, items in by_track.items():
            items.sort()
            for (_, a1, _), (b0, _, bi) in zip(items, items[1:]):
                if b0 < a1 - EPS:
                    errs.append(f"{T} overlay {bi}: overlaps the previous overlay on track '{track}'; "
                                f"move one to another track")
        for xi, x in enumerate(tl.get("texts", []), 1):
            if limits.get("no_text"):
                errs.append(f"{T} text {xi}: this job allows no text on screen")
            if x.get("role") == "caption":
                errs.append(f"{T} text {xi}: captions are added by the editor in CapCut, never in the plan")
    return errs


def main(argv: list[str]) -> None:
    if not argv or argv[0] in ("-h", "--help"):
        raise SystemExit(__doc__)
    cmd, args = argv[0], argv[1:]
    if cmd == "expand":
        src = Path(args[0])
        out_p = Path(args[args.index("--out") + 1]) if "--out" in args else src.with_name("plan.json")
        tab_p = Path(args[args.index("--table") + 1]) if "--table" in args else src.with_name("plan_table.txt")
        plan = expand(json.loads(src.read_text(encoding="utf-8")))
        out_p.write_text(json.dumps(plan, indent=1, ensure_ascii=False), encoding="utf-8")
        tab_p.write_text(plan_table(plan), encoding="utf-8")
        out = {"plan": str(out_p), "table": str(tab_p), "timelines": len(plan["timelines"]),
               "clips": sum(len(t["clips"]) for t in plan["timelines"]),
               "overlays": sum(len(t["overlays"]) for t in plan["timelines"])}
    elif cmd == "check":
        limits = json.loads(Path(args[args.index("--limits") + 1]).read_text(encoding="utf-8")) if "--limits" in args else None
        errs = check(json.loads(Path(args[0]).read_text(encoding="utf-8")), limits)
        print(json.dumps({"ok": not errs, "errors": errs}, indent=1, ensure_ascii=False))
        raise SystemExit(1 if errs else 0)
    else:
        raise SystemExit(f"unknown command {cmd!r}\n{__doc__}")
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
