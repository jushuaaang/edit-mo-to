"""Compact frame plan -> contract plan, plus the plan table.

CLI (prints JSON):
    expand <plan2.json> [--out plan.json] [--table plan_table.txt]
                         expand the compact frame plan (plan2) into the edit-plan JSON the editor builds from
"""
import json
import re
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import motion_render as mr  # noqa: E402
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
    else:
        raise SystemExit(f"unknown command {cmd!r}\n{__doc__}")
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
