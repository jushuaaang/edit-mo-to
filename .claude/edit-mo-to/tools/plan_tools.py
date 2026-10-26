"""Compact frame plan -> contract plan, plus the plan table.

CLI (prints JSON):
    expand <plan2.json> [--out plan.json] [--table plan_table.txt]
                         expand the compact frame plan (plan2) into the edit-plan JSON the editor builds from
    check <plan.json> [--limits limits.json]
                         timing, reuse, VO edges, overlay, template and scale problems, and a temp_en English
                         file whose line count differs from its timings' lines; exit code 1 when any
    prompts <prompts2.json> [--script script.txt] [--timings vo.json] [--out prompts.txt]
                         expand the compact prompt spec into the table(s) and one full prompt block per prompt
    check-prompts <prompts2.json> [--script script.txt] [--timings vo.json]
                         locks, dialogue, length vs VO span, attachments, generator limits; exit code 1 when any
    ops <old_plan.json> <new_plan.json> "<timeline>" --segments dump.json [--out ops.json]
                         clip differences between two contract plans as `capcut_project.py patch` ops (µs);
                         dump.json is `capcut_project.py segments` of the built timeline
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
from plan_common import clip_len_f, clip_volume  # noqa: E402

TRACKS = {"main": "video_main", "top": "video_top", "bottom": "video_bottom", "overlay": "video_overlay"}
TRACKS_DUMP = {"video_main": "video"}  # track names capcut_project.segments reports, where they differ
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
         "at": sec(at_f), "duration": sec(len_f), "speed": speed, "track": TRACKS[track], "x": 0.0, "y": 0.0, "scale": 1.0,
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


COLOUR_RE = re.compile(r"\s*(#[0-9a-fA-F]{3,8}|rgba?\([^)]*\)|hsla?\([^)]*\))\s*")
FONT_RE = re.compile(r"\s*[A-Za-z][A-Za-z0-9 '\-]*\s*")


def _brand_fits(key: str, value, default) -> bool:
    """A brand value fills a template var only when the var's default is the same kind of value: a colour for
    bg/fg/accent, a font family for font (badge's `accent` defaults to "" and renders as text)."""
    kind = FONT_RE if key == "font" else COLOUR_RE
    return all(isinstance(x, str) and kind.fullmatch(x) for x in (value, default))


def _overlay(row: list, shift: int, brand: dict, block: str | None, where: str) -> dict:
    if len(row) < 6:
        raise ValueError(f"{where}: overlay row needs [template, at_f, len_f, vars, track, sfx, opts?]")
    template, at_f, len_f, variables, track, sfx = row[:6]
    opts = row[6] if len(row) > 6 else {}
    at_f, len_f = _frame(at_f, f"{where} at_f"), _frame(len_f, f"{where} len_f")
    declared = mr.list_templates().get(template, {}).get("defaults", {})
    v = dict(variables)
    for k in BRAND_KEYS:
        if k in brand and k in declared and k not in v and _brand_fits(k, brand[k], declared[k]):
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


TEXT_STYLES = ("badge", "word", "cta")   # the editor's add_text presets (build_project.TEXT_STYLES)


def _text(row: list, shift: int, block: str | None, where: str) -> dict:
    if len(row) < 4:
        raise ValueError(f"{where}: text row needs [text, at_f, len_f, style, opts?]")
    text, at_f, len_f, style = row[:4]
    if style not in TEXT_STYLES:
        raise ValueError(f"{where}: unknown text style {style!r}; use {list(TEXT_STYLES)}")
    t = {"text": text, "at": sec(_frame(at_f, f"{where} at_f") + shift), "duration": sec(_frame(len_f, f"{where} len_f")),
         "style": style, **(row[4] if len(row) > 4 else {})}
    if block:
        t["block"] = block
    return t


def _timeline(tl: dict, plan2: dict) -> dict:
    base, brand, blocks = plan2.get("base", ""), plan2.get("brand", {}), plan2.get("blocks", {})
    name = tl["name"]
    clips, overlays, effects, texts = [], [], [], []
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
        texts += [_text(r, shift, block, where) for r in body.get("texts", [])]
    end_f = max((c["_end_f"] for c in clips), default=0)
    for c in clips:
        del c["_end_f"]
    vo = tl["vo"] if "vo" in tl else plan2.get("vo")              # a timeline's own VO / music wins
    music = tl["music"] if "music" in tl else plan2.get("music")
    out = {"name": name,
           "vo": _join(base, vo["file"]) if vo else None,
           "vo_in": sec(_frame(tl.get("vo_in_f", 0), f"{name} vo_in_f")),
           "vo_out": sec(_frame(tl.get("vo_out_f", end_f), f"{name} vo_out_f")),
           "vo_volume": vo.get("volume", 1.0) if vo else 1.0,
           "music": _join(base, music["file"]) if music else None,
           "music_volume": music.get("volume", 0.1) if music else 0.1,
           "clips": clips, "overlays": overlays, "texts": texts, "manual": tl.get("manual", [])}
    if effects:
        out["effects"] = effects
    if "temp_en" in tl:   # a timeline's own English lines and timings (e.g. a hook with its own VO)
        out["temp_en"] = _temp_en(tl["temp_en"], base)
    if "temp_en_removed" in tl:   # the editor deleted TEMP_EN on this timeline only
        out["temp_en_removed"] = tl["temp_en_removed"]
    if tl.get("captions"):   # a timeline's own step-10 script and VO timings (e.g. a hook with its own VO)
        out["captions"] = _captions(tl["captions"], base)
    return out


def _temp_en(te: dict | None, base: str, vo: dict | None = None) -> dict | None:
    """{"english": <script_en.txt>, "timings": <vo.json>} with both paths joined to base (None stays None);
    the plan-wide one also records the VO file its timings belong to ("vo"), for check."""
    if not te:
        return None
    out = {k: _join(base, te[k]) for k in ("english", "timings")}
    if vo:
        out["vo"] = _join(base, vo["file"])
    return out


def _captions(c: dict, base: str, vo: dict | None = None) -> dict:
    """{"script": <script.txt>, "timings": <vo.json>} with both paths joined to base; the plan-wide one also
    records the VO file its timings belong to ("vo"), so captions.caption_inputs never uses them on another VO."""
    out = {k: _join(base, c[k]) for k in ("script", "timings") if c.get(k)}
    if vo:
        out["vo"] = _join(base, vo["file"])
    return out


def expand(plan2: dict) -> dict:
    """Compact frame plan (plan2) -> contract plan: frames become 10-decimal seconds, blocks are resolved,
    brand vars are filled into the overlays whose template declares them."""
    plan = {k: plan2[k] for k in ("project", "style", "fps", "width", "height", "base", "brand") if k in plan2}
    if "temp_en" in plan2:
        plan["temp_en"] = _temp_en(plan2["temp_en"], plan2.get("base", ""), plan2.get("vo"))
    if plan2.get("captions"):
        plan["captions"] = _captions(plan2["captions"], plan2.get("base", ""), plan2.get("vo"))
    for k in ("temp_en_removed", "captions_style"):
        if k in plan2:
            plan[k] = plan2[k]
    plan["timelines"] = [_timeline(tl, plan2) for tl in plan2.get("timelines", [])]
    return plan


def _temp_en_errors(te: dict, where: str) -> list[str]:
    """The English file must have one line per script line; the plan has no script, so the count comes from
    the `lines` of the VO timings the build reads."""
    from captions import _lines
    try:
        n_script = len(json.loads(Path(te["timings"]).read_text(encoding="utf-8-sig")).get("lines") or [])
        n_en = len(_lines(te["english"]))
    except (OSError, ValueError, KeyError, TypeError) as e:
        return [f"{where}: cannot read {te}: {e}"]
    if n_en != n_script:
        return [f"{where}: {n_en} English lines in {te['english']} but {n_script} script lines in {te['timings']}; "
                f"write one English line per script line"]
    return []


def plan_table(plan: dict) -> str:
    head = ["#", "Timeline", "At", "Len", "File", "Src in–out", "Speed", "Layout", "Transition/Effect", "Line"]
    rows = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    n = 0
    for tl in plan["timelines"]:
        for c in tl["clips"]:
            n += 1
            ln = _clip_len(c)
            fx = " ".join(str(x) for x in (c.get("transition"), c.get("effect")) if x)
            rows.append("| " + " | ".join(_cell(x) for x in [
                n, tl["name"], to_sf(c["at"]), to_sf(ln), c["file"], f"{to_sf(c['src_in'])}–{to_sf(c['src_out'])}",
                f"{c['speed']:g}x", c.get("layout") or c["track"], fx, c.get("line", "")]) + " |")
    return "\n".join(rows)


CANVAS = (1080, 1920)   # the 9:16 default when a plan gives no width/height
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
    """Timeline length in seconds of whole frames: the clip's `duration` (len_f), the same length the build
    places (plan_common.clip_len_f)."""
    return clip_len_f(c) / 30


def canvas(plan: dict) -> tuple[int, int]:
    return int(plan.get("width") or CANVAS[0]), int(plan.get("height") or CANVAS[1])


def ratio(text) -> tuple[float, float] | None:
    """limits.json `ratio` ("9:16", "1:1", "4:5") -> (w, h), or None when absent or unreadable."""
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*[:x/]\s*(\d+(?:\.\d+)?)\s*", str(text or ""))
    return (float(m.group(1)), float(m.group(2))) if m and float(m.group(2)) else None


def _scale_errors(c: dict, info: dict, where: str, cv: tuple[int, int] = CANVAS) -> list[str]:
    errs = []
    scale = c.get("scale", 1.0)
    if scale > 2.0 and not c.get("allow_scale"):
        errs.append(f"{where}: scale {scale} is above 2.0; set allow_scale if the punch-in is meant")
    w, h = info.get("width"), info.get("height")
    if w and h and c.get("track") not in SPLIT_TRACKS:
        if abs(info.get("rotation", 0)) % 180 == 90:
            w, h = h, w
        f = min(cv[0] / w, cv[1] / h)
        if scale * w * f < cv[0] * 0.99 or scale * h * f < cv[1] * 0.99:   # 1% slack: 320x568 is "9:16"
            errs.append(f"{where}: scale {scale} leaves black edges on a {w}x{h} source "
                        f"(fitted {round(w * f)}x{round(h * f)} in a {cv[0]}x{cv[1]} canvas); "
                        f"use scale >= {max(cv[0] / (w * f), cv[1] / (h * f)):.2f}")
    return errs


def _overlay_errors(o: dict, n: int, cuts: list[float], tl: str, templates: dict, limits: dict,
                    cv: tuple[int, int] = CANVAS) -> list[str]:
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
            in_band = top is not None and float(top) >= cv[1] - band
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
    Each error starts with `T<n> clip <m>:`, `T<n> overlay <m>:` or `T<n> vo:` (1-based), or `plan:`.
    The canvas is the plan's width x height; limits `ratio` only cross-checks it."""
    limits, errs, info = limits or {}, [], {}
    templates = mr.list_templates()
    cv = canvas(plan)
    want = ratio(limits.get("ratio"))
    if want and abs(cv[0] / cv[1] - want[0] / want[1]) > 0.01:
        errs.append(f"plan: canvas {cv[0]}x{cv[1]} is not the brief's ratio {limits['ratio']}; set width/height in plan2")

    def media(path):
        if path not in info:
            try:
                info[path] = probe(path)
            except Exception as e:
                info[path] = e
        return info[path]

    if plan.get("temp_en") and not plan.get("temp_en_removed"):
        errs += _temp_en_errors(plan["temp_en"], "plan: temp_en")
    seen = []   # (timeline label, clip number, clip) of every clip so far, for reuse checks
    for ti, tl in enumerate(plan.get("timelines", []), 1):
        T = f"T{ti}"
        clips = tl.get("clips", [])
        for ci, c in enumerate(clips, 1):
            where = f"{T} clip {ci}"
            for k in ("at", "src_in", "src_out"):
                if not _whole(c[k]):
                    errs.append(f"{where}: {k} {c[k]} is not a whole frame at 30 fps")
            m = media(c["file"])
            if isinstance(m, Exception):
                errs.append(f"{where}: cannot read {c['file']}: {m}")
            else:
                if c["src_out"] > m["duration"] + 1 / 30 + EPS:
                    errs.append(f"{where}: src_out {c['src_out']} is past the file end {m['duration']} ({c['file']})")
                errs += _scale_errors(c, m, where, cv)
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
        end_f = None   # furthest end so far, in frames: a nested clip must not hide a later overlap
        for b, bi in main:
            at_f = round(b["at"] * 30)
            if end_f is not None and at_f > end_f:
                errs.append(f"{T} clip {bi}: gap on the main track; the previous clip ends at {round(end_f / 30, 4)}, "
                            f"this one starts at {b['at']}")
            elif end_f is not None and at_f < end_f:
                errs.append(f"{T} clip {bi}: overlaps the previous main-track clip (it ends {round(end_f / 30, 4)}, "
                            f"this one starts {b['at']})")
            end_f = max(end_f or 0, at_f + round(_clip_len(b) * 30))
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
        te_off = plan.get("temp_en_removed") or tl.get("temp_en_removed")
        if tl.get("temp_en") and not te_off:
            errs += _temp_en_errors(tl["temp_en"], f"{T} temp_en")
        te = plan.get("temp_en") or {}
        # a plan-wide temp_en with no plan VO recorded is timed to some other VO: every own-VO timeline differs
        if te and "temp_en" not in tl and tl.get("vo") and tl["vo"] != te.get("vo") and not te_off:
            errs.append(f"{T} temp_en: this timeline has its own VO ({tl['vo']}) but uses the plan's English lines, "
                        f"timed to {te.get('vo') or 'another VO (plan2 has no top-level vo)'}; give it its own "
                        f"temp_en (english + timings), or temp_en: null")
        cuts, by_track = [c["at"] for c in clips], {}
        for oi, o in enumerate(tl.get("overlays", []), 1):
            errs += _overlay_errors(o, oi, cuts, T, templates, limits, cv)
            if o.get("cutout"):   # the build cuts the person out of the one main-track clip under it
                a, b = round(o["at"] * 30), round((o["at"] + o["duration"]) * 30)
                if not any(c.get("track", "video_main") == "video_main" and round(c["at"] * 30) <= a
                           and b <= round(c["at"] * 30) + clip_len_f(c) for c in clips):
                    errs.append(f"{T} overlay {oi}: cutout {a}-{b} (frames) does not lie inside one main-track clip; "
                                f"move it or shorten it to one clip")
            by_track.setdefault(o["track"], []).append((o["at"], o["at"] + o["duration"], oi))
        for track, items in by_track.items():
            items.sort()
            reach = None   # furthest end so far: a nested overlay must not hide a later overlap
            for b0, b1, bi in items:
                if reach is not None and b0 < reach - EPS:
                    errs.append(f"{T} overlay {bi}: overlaps the previous overlay on track '{track}'; "
                                f"move one to another track")
                reach = b1 if reach is None else max(reach, b1)
        for xi, x in enumerate(tl.get("texts", []), 1):
            if limits.get("no_text"):
                errs.append(f"{T} text {xi}: this job allows no text on screen")
            if x.get("role") == "caption":
                errs.append(f"{T} text {xi}: captions are never in the plan: no captions before step 10, except the "
                            f"TEMP_EN_delete_me review track (the build adds it from temp_en)")
    return errs


REQUIRED_LOCKS = {
    "ugc": ["realism", "product", "notext", "voice", "look", "pacing"],
    "broll": ["realism", "notext"],
    "pixar": ["style_bible", "notext", "voice"],
    "claymation": ["style_bible", "notext", "voice"],
    "product-ad": ["product", "notext"],
}
IMAGE_KINDS = {"keyframe", "character"}
IMAGE_DROP = {"voice", "pacing"}          # a still has no voice and no pacing
CHARACTER_DROP = IMAGE_DROP | {"product"}  # a character sheet shows the person, not the product


def required_locks(style: str, kind: str) -> list[str]:
    """The locks a prompt of this kind needs in this style: video prompts all of REQUIRED_LOCKS, keyframes
    all but voice and pacing, character sheets also without product."""
    drop = CHARACTER_DROP if kind == "character" else IMAGE_DROP if kind in IMAGE_KINDS else set()
    return [k for k in REQUIRED_LOCKS[style] if k not in drop]
CLIENT = "client"   # a picked client clip: a table row (file + cut), no prompt block, no lock rules
FPS = 30


def _kind(p: dict) -> str:
    return p.get("kind", "video")


def _is_seedance(spec: dict) -> bool:
    return "seedance" in (spec.get("mode"), spec.get("generator"))


def _lock_text(spec: dict, p: dict, name: str) -> str:
    return (p.get("lock_overrides") or {}).get(name) or spec.get("locks", {}).get(name, "")


def _span_f(s: str) -> int | None:
    """'0:00-2:12' (seconds:frames) -> length in frames, or None when unparseable."""
    m = re.fullmatch(r"\s*(\d+):(\d+)\s*-\s*(\d+):(\d+)\s*", s or "")
    if not m:
        return None
    a, b, c, d = map(int, m.groups())
    return (c * FPS + d) - (a * FPS + b)


def _line_text(script_lines: list[str], p: dict) -> str | None:
    n = p.get("line")
    return script_lines[n - 1] if isinstance(n, int) and 1 <= n <= len(script_lines) else None


def check_prompts(spec: dict, script_lines: list[str], timings: dict | None) -> list[str]:
    """Problems in a prompts2 spec: locks, attachments, generator limits, dialogue and length vs the VO span."""
    style = spec.get("style", "ugc")
    if style not in REQUIRED_LOCKS:
        return [f"unknown style {style!r} (one of {', '.join(REQUIRED_LOCKS)})"]
    errs: list[str] = []
    seedance = _is_seedance(spec)
    keys = set(spec.get("attach", {}))
    video = []
    for p in spec.get("prompts", []):
        w = f"prompt {p.get('id', '?')}"
        if _kind(p) == CLIENT:
            if not p.get("file"):
                errs.append(f"{w}: client row needs the clip's file")
            cut_ok = all(isinstance(p.get(k), int) for k in ("in_f", "out_f")) and p["out_f"] > p["in_f"]
            if not cut_ok:
                errs.append(f"{w}: client row needs whole-frame in_f < out_f (the cut in the clip)")
            if style == "product-ad":      # no script, no VO: placed on the beats in the edit plan
                continue
            if _line_text(script_lines, p) is None:
                errs.append(f"{w}: line {p.get('line')!r} is not in the script ({len(script_lines)} lines)")
            if p.get("vo_in_f") is None or p.get("vo_out_f") is None:
                errs.append(f"{w}: vo_in_f and vo_out_f are required")
            else:
                video.append(p)
                cut_f = (p["out_f"] - p["in_f"]) * FPS / p.get("fps", FPS) if cut_ok else None
                if cut_f is not None and abs(cut_f - (p["vo_out_f"] - p["vo_in_f"])) > 2:
                    errs.append(f"{w}: cut {p['in_f']}-{p['out_f']} is {round(cut_f)} timeline frames, not the "
                                f"{p['vo_out_f'] - p['vo_in_f']}-frame VO span (±2)")
            continue
        have = p.get("locks", [])
        missing = [k for k in required_locks(style, _kind(p)) if k not in have]
        if missing:
            errs.append(f"{w}: missing locks: {', '.join(missing)}")
        for k in have:
            if not _lock_text(spec, p, k):
                errs.append(f"{w}: lock {k!r} has no text in locks (or lock_overrides)")
        for a in p.get("attach", []):
            if a not in keys:
                errs.append(f"{w}: attach {a} is not defined in the spec's attach")
        if _kind(p) in IMAGE_KINDS:
            continue
        gl = p.get("gen_len_s")
        if not seedance and len(p.get("attach", [])) > 7:
            errs.append(f"{w}: Flow allows 7 attachments at most, has {len(p['attach'])}")
        if gl is not None:
            if not seedance and not 4 <= gl <= 8:
                errs.append(f"{w}: Flow generation must be 4–8 s, got {gl} s")
            if seedance and gl < 4:
                errs.append(f"{w}: Seedance clips must be at least 4 s, got {gl} s")
        if style == "product-ad":
            continue
        video.append(p)
        text = _line_text(script_lines, p)
        if text is None:
            errs.append(f"{w}: line {p.get('line')!r} is not in the script ({len(script_lines)} lines)")
        elif p.get("dialogue") and " ".join(p["dialogue"].split()) not in " ".join(text.split()):
            errs.append(f"{w}: dialogue is not a verbatim part of script line {p['line']}")
        i, o = p.get("vo_in_f"), p.get("vo_out_f")
        if i is None or o is None:
            errs.append(f"{w}: vo_in_f and vo_out_f are required")
            continue
        span = o - i
        if gl is not None and abs(gl * FPS - span) > 2:
            if gl * FPS < span:
                errs.append(f"{w}: generated {gl} s is shorter than the {span}-frame VO span")
            elif not p.get("use"):
                errs.append(f"{w}: generated {gl} s is longer than the {span}-frame VO span, so it needs a use span")
            else:
                u = _span_f(p["use"])
                if u is None or abs(u - span) > 2:
                    errs.append(f"{w}: use {p['use']!r} must be s:ff-s:ff and match the VO span within ±2 frames")
    errs += _line_cover_errors(video, timings)
    last: dict = {}
    for p in video:
        if p.get("optional") or not isinstance(p.get("line"), int) or p.get("vo_in_f") is None or p.get("vo_out_f") is None:
            continue
        prev = last.get(p["line"])
        if prev and p["vo_in_f"] < prev["vo_out_f"] - 2:
            errs.append(f"prompts {prev['id']} and {p['id']} share line {p['line']} without a cut point between words")
        last[p["line"]] = p
    return errs


def _line_cover_errors(rows: list[dict], timings: dict | None) -> list[str]:
    """Rows on one script line (AI prompts and client cuts) must together cover its VO span within ±2 frames,
    each inside it; a single row's span must match the line. Optional rows are checked on their own."""
    tl = (timings or {}).get("lines", [])
    errs, groups = [], {}
    for p in rows:
        n = p.get("line")
        if isinstance(n, int) and 1 <= n <= len(tl) and p.get("vo_in_f") is not None and p.get("vo_out_f") is not None:
            groups.setdefault((n, p["id"]) if p.get("optional") else (n,), []).append(p)
    for key, ps in groups.items():
        n = key[0]
        ti, to = round(tl[n - 1]["start"] * FPS), round(tl[n - 1]["end"] * FPS)
        i, o = min(p["vo_in_f"] for p in ps), max(p["vo_out_f"] for p in ps)
        if len(ps) == 1 and (abs(i - ti) > 2 or abs(o - to) > 2):
            errs.append(f"prompt {ps[0]['id']}: VO span {i}-{o} is not within ±2 frames of line {n} ({ti}-{to})")
        elif len(ps) > 1:
            ids = ", ".join(p["id"] for p in ps)
            covered = sum(p["vo_out_f"] - p["vo_in_f"] for p in ps)
            if abs(i - ti) > 2 or abs(o - to) > 2 or covered < (o - i) - 2 * len(ps):
                errs.append(f"prompts {ids}: together cover {i}-{o} ({covered} frames), not line {n} "
                            f"({ti}-{to}) within ±2 frames")
            for p in ps:
                if p["vo_in_f"] < ti - 2 or p["vo_out_f"] > to + 2:
                    errs.append(f"prompt {p['id']}: VO span {p['vo_in_f']}-{p['vo_out_f']} runs outside line {n} ({ti}-{to})")
    return errs


def _cell(t) -> str:
    return str(t).replace("|", "\\|").replace("\n", " ")


def _words(t: str) -> list[str]:
    return re.findall(r"[\w']+", (t or "").lower())


def _quoted_in(dialogue: str, action: str) -> bool:
    """True when every word of the dialogue appears, in order, in the action's per-second windows."""
    it = iter(_words(action))
    return bool(_words(dialogue)) and all(w in it for w in _words(dialogue))


def _block(spec: dict, p: dict) -> str:
    parts = ["Start on @Image1."] if _is_seedance(spec) and _kind(p) == "video" else []
    for label, key in (("Subject", "subject"), ("Setting", "setting"), ("Action", "action"),
                       ("Camera", "camera"), ("Look", "look")):
        if p.get(key):
            parts.append(f"{label}: {p[key]}")
    if p.get("dialogue") and not _quoted_in(p["dialogue"], p.get("action", "")):   # the words once per prompt
        parts.append(f"Dialogue: {p['dialogue']}")
    parts += [_lock_text(spec, p, k) for k in p.get("locks", [])]
    if p.get("attach"):
        att = spec.get("attach", {})
        parts.append("Attach: " + ", ".join(f"{a} = {att[a]}" if a in att else a for a in p["attach"]))
    if p.get("negative"):
        parts.append(f"Negative: {p['negative']}")
    return "\n".join(parts)


def render_prompts(spec: dict, script_lines: list[str], timings: dict | None) -> str:
    """The prompts deliverable: table(s), one fenced block per prompt with locks in full, then notes."""
    prompts = spec.get("prompts", [])
    rows = [p for p in prompts if _kind(p) in ("video", CLIENT)]
    if spec.get("style") == "product-ad":   # no script: beat order when every row has an at_f, else spec order
        vids = sorted(rows, key=lambda p: p["at_f"]) if all(isinstance(p.get("at_f"), int) for p in rows) else rows
    else:                                   # script order, AI and client rows together
        vids = sorted(rows, key=lambda p: (p["line"] if isinstance(p.get("line"), int) else 10 ** 6, p.get("vo_in_f") or 0))
    imgs = [p for p in prompts if _kind(p) in IMAGE_KINDS]
    out: list[str] = []
    if vids:
        out += ["| # | Script line | VO in | VO out | Length | Source | Prompt / Cut | Attach |", "|---|---|---|---|---|---|---|---|"]
        for p in vids:
            i, o = p.get("vo_in_f"), p.get("vo_out_f")
            length = f"{(o - i) / FPS:.2f} s" if i is not None and o is not None else ""
            if p.get("gen_len_s") is not None:
                length += f" (gen {p['gen_len_s']} s)"
            cut = f"use {p['use']}" if p.get("use") else "whole clip"
            if p.get("optional"):
                cut += " (optional)"
            line = _line_text(script_lines, p)
            if _kind(p) == CLIENT:
                fps = round(p.get("fps", FPS))   # in_f/out_f count the clip's own frames
                src = f"{p['slot']}: {p['file']}" if p.get("slot") else p.get("file", "")
                cut = f"{to_sf(p['in_f'] / fps, fps)}–{to_sf(p['out_f'] / fps, fps)}" + (f" ({fps:g} fps)" if fps != FPS else "")
                out.append("| " + " | ".join(_cell(c) for c in (
                    p["id"], f"{p.get('line', '')}: {line}" if line else p.get("line", ""),
                    to_sf(i / FPS) if i is not None else "", to_sf(o / FPS) if o is not None else "",
                    length, src, cut, "")) + " |")
                continue
            out.append("| " + " | ".join(_cell(c) for c in (
                f"{p['id']} (generate)", f"{p.get('line', '')}: {line}" if line else p.get("line", ""),
                to_sf(i / FPS) if i is not None else "", to_sf(o / FPS) if o is not None else "",
                length, spec.get("generator", ""), cut, ", ".join(p.get("attach", [])))) + " |")
        out.append("")
    if imgs:
        out += ["| # | Script line | Shot | Save as |", "|---|---|---|---|"]
        for p in imgs:
            line = _line_text(script_lines, p)
            out.append("| " + " | ".join(_cell(c) for c in (
                p["id"], f"{p.get('line', '')}: {line}" if line else p.get("line", ""),
                p.get("subject") or p.get("action") or "", f"{p['id']}.png")) + " |")
        out.append("")
    for p in (q for q in prompts if _kind(q) != CLIENT):
        out += [f"**{p['id']}**", "```", _block(spec, p), "```", ""]
    notes = spec.get("notes")
    if notes:
        out += ["Notes", *[f"- {n}" for n in ([notes] if isinstance(notes, str) else notes)], ""]
    return "\n".join(out)


def _norm_path(p: str) -> str:
    p = p.replace("\\", "/")
    return p.casefold() if re.match(r"^[A-Za-z]:/", p) else p


def _us(frame: int) -> int:
    return round(frame * 1e6 / 30)


def _facts(c: dict) -> dict:
    """A contract clip as whole frames plus the patch units it maps to."""
    speed = float(c.get("speed") or 1.0)
    at_f = round(c["at"] * 30)
    len_f = clip_len_f(c)
    vol = clip_volume(c)
    dur = _us(at_f + len_f) - _us(at_f)
    return {"file": c["file"], "track": c.get("track", "video_main"), "src_in_f": round(c["src_in"] * 30),
            "start": _us(at_f), "duration": dur, "src_duration": round(dur * speed), "speed": speed,
            "scale": c.get("scale", 1.0), "x": c.get("x", 0.0), "y": c.get("y", 0.0), "volume": vol,
            "src_start": round(c["src_in"] * 1e6), "at": c["at"], "src_in": c["src_in"]}


def _pair_rows(old: list[dict], new: list[dict]) -> tuple[list, list, list]:
    """Old and new clip rows with the same track, file and source frame belong together (in time order)."""
    groups: dict = {}
    for side, rows in (("o", old), ("n", new)):
        for r in sorted(rows, key=lambda r: r["start"]):
            groups.setdefault((r["track"], _norm_path(r["file"]), r["src_in_f"]), {"o": [], "n": []})[side].append(r)
    pairs, gone, added = [], [], []
    for g in groups.values():
        k = min(len(g["o"]), len(g["n"]))
        pairs += list(zip(g["o"][:k], g["n"][:k]))
        gone += g["o"][k:]
        added += g["n"][k:]
    return pairs, gone, added


def _find_segment(row: dict, segs: list[dict], used: set) -> dict | None:
    want = TRACKS_DUMP.get(row["track"], row["track"])
    best = [s for s in segs if s["id"] not in used and s.get("track") == want and s.get("source")
            and _norm_path(s["source"]) == _norm_path(row["file"]) and s.get("src_in") is not None
            and abs(s["src_in"] * 30 - row["src_in_f"]) <= 1 + 1e-6]
    return min(best, key=lambda s: abs(s["at"] - row["at"]), default=None)


def ops(old_plan: dict, new_plan: dict, timeline: str, dump: dict) -> dict:
    """Clip differences between the built plan and the revised plan as `capcut_project.py patch` ops, with
    each old clip row found on the built timeline (`dump` = capcut_project.segments) by track, source path and
    source frame. Only clips are diffed: overlays and SFX go through add-overlay / add-tracks. A row that
    needs an op but whose segment cannot be found goes to "unmapped" and gets no op (nothing is guessed);
    unchanged rows are never reported."""
    def clips(plan):
        found = [t for t in plan.get("timelines", []) if t.get("name") == timeline]
        if not found:
            raise ValueError(f"no timeline named {timeline!r} in the plan; have {[t.get('name') for t in plan.get('timelines', [])]}")
        return [_facts(c) for c in found[0].get("clips", [])]

    pairs, gone, added = _pair_rows(clips(old_plan), clips(new_plan))
    segs = [s for s in dump.get("segments", []) if s.get("id")]
    used: set = set()
    out, unmapped = [], []

    def label(r):
        return f"{r['file']} src_in {r['src_in']} at {r['at']}"

    def locate(r):
        seg = _find_segment(r, segs, used)
        if seg is None:
            unmapped.append({"row": label(r), "why": "no segment on the timeline with this source and source frame "
                                                     "(placeholder path, moved or removed by hand)"})
        else:
            used.add(seg["id"])
        return seg

    for o, n in sorted(pairs, key=lambda p: p[0]["start"]):
        changed = {}
        if n["start"] != o["start"]:
            changed["start"] = n["start"]
        if (n["duration"], n["speed"]) != (o["duration"], o["speed"]):
            changed.update(duration=n["duration"], src_duration=n["src_duration"])
        if n["speed"] != o["speed"]:
            changed["speed"] = n["speed"]
        changed.update({k: n[k] for k in ("scale", "x", "y", "volume") if n[k] != o[k]})
        if changed:
            seg = locate(o)
            if seg:
                out.append({"op": "set", "id": seg["id"], **changed})
    for o in sorted(gone, key=lambda r: r["start"]):
        seg = locate(o)
        if seg:
            out.append({"op": "remove", "id": seg["id"]})
    for n in sorted(added, key=lambda r: r["start"]):
        out.append({"op": "insert", "track": TRACKS_DUMP.get(n["track"], n["track"]), "file": n["file"],
                    "start": n["start"], "duration": n["duration"], "src_start": n["src_start"],
                    "speed": n["speed"], "scale": n["scale"], "x": n["x"], "y": n["y"], "volume": n["volume"]})
    return {"ops": out, "unmapped": unmapped}


def main(argv: list[str]) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")   # Windows consoles default to cp1252
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
    elif cmd == "ops":
        def arg(k):
            return args[args.index(k) + 1] if k in args else None
        if len(args) < 3 or not arg("--segments"):
            raise SystemExit(__doc__)
        load = lambda f: json.loads(Path(f).read_text(encoding="utf-8"))  # noqa: E731
        res = ops(load(args[0]), load(args[1]), args[2], load(arg("--segments")))
        out_p = Path(arg("--out") or Path(args[1]).with_name("ops.json"))
        out_p.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
        out = {"ops_file": str(out_p), "ops": len(res["ops"]), "unmapped": res["unmapped"]}
    elif cmd in ("prompts", "check-prompts"):
        def opt(k):
            return args[args.index(k) + 1] if k in args else None
        spec = json.loads(Path(args[0]).read_text(encoding="utf-8"))
        lines = [l for l in Path(opt("--script")).read_text(encoding="utf-8").splitlines() if l.strip()] if opt("--script") else []
        timings = json.loads(Path(opt("--timings")).read_text(encoding="utf-8")) if opt("--timings") else None
        errs = check_prompts(spec, lines, timings)
        if cmd == "check-prompts":
            print(json.dumps({"ok": not errs, "errors": errs}, indent=1, ensure_ascii=False))
            raise SystemExit(1 if errs else 0)
        out_p = Path(opt("--out") or Path(args[0]).with_name("prompts.txt"))
        out_p.write_text(render_prompts(spec, lines, timings), encoding="utf-8")
        out = {"prompts": str(out_p), "count": len(spec.get("prompts", [])), "errors": errs}
    else:
        raise SystemExit(f"unknown command {cmd!r}\n{__doc__}")
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
