"""Mechanical build QA: every build-gate check of qa.md that needs no eyes, reporting only failures.

CLI (prints JSON {"rows": [...], "passed": N, "verdict": ...}; exit code 1 on a FAIL verdict):
    build <plan.json> "<project>" [--timelines "A,B"] [--changed 3,7,ov2] [--limits limits.json] [--search dir ...]
                         clips/overlays present at their time and length, extras, tracks and volumes, VO span and
                         edges, rotation, layout, overlays on cuts, reuse, dead stretches, talking head > 5 s,
                         SFX repeats, music level, duration, canvas, captions, unknown sources.
                         --changed limits present/extras/overlay_on_cut/reuse to those clips (numbers) and
                         overlays (ovN) and their neighbours, and prefixes the verdict with DELTA
    prompts <prompts2.json> [--script script.txt] [--timings t.json]
                         plan_tools.check_prompts, as the same row format
Rows are FAIL (counts toward the verdict) or OPEN (for the user to look at). `passed` counts the checks that ran
and produced no rows.
"""
import json
import re
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import capcut_project as cp  # noqa: E402
import plan_tools as pt  # noqa: E402
from media_timing import to_sf  # noqa: E402
from plan_common import clip_volume  # noqa: E402

F = 1 / 30
TOL = 2 * F + 1e-6            # clip time and length tolerance: 2 frames
CUT_TOL = F + 1e-6            # overlay start on a cut: 1 frame
DEAD_S = 2.2
HEAD_S = 5.0
MUSIC_RANGE = (0.05, 0.2)
DELTA_CHECKS = {"present", "extras", "overlay_on_cut", "reuse", "vo_span"}
ALL_CHECKS = ["present", "extras", "tracks_volumes", "vo_span", "rotation", "layout", "overlay_on_cut", "reuse",
              "dead_stretch", "talking_head_5s", "sfx_repeat", "music_level", "duration", "canvas", "captions",
              "unknown_source"]
OPEN_CHECKS = {"rotation", "dead_stretch", "music_level"}   # advisory: the user looks, the verdict ignores them
B_ROLL_TRACKS = {"video_top", "video_bottom", "video_overlay"}


def _norm(path) -> str:
    p = str(path).replace("\\", "/")
    return p.casefold() if sys.platform == "win32" else p


def _is_placeholder(seg: dict) -> bool:
    src = seg.get("source")
    return (not src and bool(seg.get("path") or seg.get("remote_url"))) or "_draftpath_placeholder" in str(src or "")


def _kind(seg: dict) -> str:
    """text | audio | overlay (HyperFrames render on overlay_*) | clip (a plan clip on any video track)."""
    name = str(seg.get("track") or "")
    if seg.get("track_type") == "text" or seg.get("material_type") == "texts" or seg.get("text") is not None:
        return "text"
    if seg.get("track_type") == "audio":
        return "audio"
    return "overlay" if name.startswith("overlay_") else "clip"


def _expected_track(c: dict) -> str:
    return "video" if c.get("track", "video_main") == "video_main" else c["track"]


def _expected_volume(c: dict) -> float:
    return float(clip_volume(c))


def _in_changed(spec: list[str], n: int, kind: str) -> bool:
    return (f"ov{n}" if kind == "ov" else str(n)) in spec


def _neighbours(items: list[dict], hit: set[int]) -> set[int]:
    """Indexes of `hit` plus the items either side of each in start order."""
    order = sorted(range(len(items)), key=lambda i: items[i]["at"])
    out = set(hit)
    for pos, i in enumerate(order):
        if i in hit:
            out.update(order[max(pos - 1, 0):pos + 2])
    return out


class _Rows:
    def __init__(self):
        self.rows, self.ran = [], set()

    def add(self, check, evidence, fix, timeline, status=None):
        self.rows.append({"n": len(self.rows) + 1, "check": check,
                          "status": status or ("OPEN" if check in OPEN_CHECKS else "FAIL"),
                          "evidence": evidence, "fix": fix, "timeline": timeline})


def _match_clips(clips: list[dict], segs: list[dict]) -> dict[int, dict]:
    """Plan clip index -> its segment, matched on source + src_in (within 1 frame), each segment once."""
    used, out = set(), {}
    for i, c in enumerate(clips):
        best = None
        for j, s in enumerate(segs):
            if j in used or s.get("source") is None or _norm(s["source"]) != _norm(c["file"]):
                continue
            if abs((s.get("src_in") or 0.0) - c["src_in"]) > CUT_TOL:
                continue
            if best is None or abs(s["at"] - c["at"]) < abs(segs[best]["at"] - c["at"]):
                best = j
        if best is not None:
            used.add(best)
            out[i] = segs[best]
    return out


def _match_overlays(overlays: list[dict], segs: list[dict]) -> dict[int, dict]:
    used, out = set(), {}
    for i, o in enumerate(overlays):
        cands = [(abs(s["at"] - o["at"]), j) for j, s in enumerate(segs) if j not in used and abs(s["at"] - o["at"]) <= TOL]
        if cands:
            j = min(cands)[1]
            used.add(j)
            out[i] = segs[j]
    return out


def check_build(plan: dict, project: Path, timelines: list[str] | None = None, changed: list[str] | None = None,
                limits: dict | None = None, segments_fn=None, probe=None, silent=None, search=()) -> dict:
    segments_fn = segments_fn or cp.segments
    probe = probe or pt.probe_media
    silent = silent or pt.edge_silent
    limits = limits or {}
    delta = changed is not None
    out = _Rows()
    todo = [tl for tl in plan.get("timelines", []) if not timelines or tl["name"] in timelines]
    ran = set(DELTA_CHECKS) if delta else set(ALL_CHECKS)
    if not delta:
        if not limits.get("min_s") and not limits.get("max_s"):
            ran.discard("duration")
        if not any(tl.get("music") for tl in todo):
            ran.discard("music_level")
    entries = []   # reuse: (timeline name, label, {file, src_in, src_out}, exempt, in delta)

    for tl in todo:
        name, clips, overlays = tl["name"], tl.get("clips", []), tl.get("overlays", [])
        dump = segments_fn(project, name, list(search))
        segs = dump.get("segments", [])
        by_kind = {k: [s for s in segs if _kind(s) == k] for k in ("clip", "overlay", "audio", "text")}
        matched = _match_clips(clips, by_kind["clip"])
        matched_ov = _match_overlays(overlays, by_kind["overlay"])

        keep_c, keep_o = set(range(len(clips))), set(range(len(overlays)))
        window = None
        if delta:
            hit_c = {i for i in range(len(clips)) if _in_changed(changed, i + 1, "c")}
            hit_o = {i for i in range(len(overlays)) if _in_changed(changed, i + 1, "ov")}
            keep_c = _neighbours(clips, hit_c)
            keep_o = _neighbours(overlays, hit_o)
            spans = [(clips[i]["at"], clips[i]["at"] + pt._clip_len(clips[i])) for i in keep_c]
            spans += [(overlays[i]["at"], overlays[i]["at"] + overlays[i]["duration"]) for i in keep_o]
            window = spans

        def in_window(s):
            return window is None or any(s["at"] < b - 1e-6 and s["at"] + s["duration"] > a + 1e-6 for a, b in window)

        def add(check, evidence, fix, status=None):
            out.add(check, evidence, fix, name, status)

        # unknown_source: a placeholder path never matches anything, so say so instead of failing the match
        if "unknown_source" in ran:
            seen = set()
            for s in segs:
                if _kind(s) != "text" and _is_placeholder(s):
                    key = s.get("path") or s.get("source")
                    if key not in seen:
                        seen.add(key)
                        add("unknown_source", f"segment at {to_sf(s['at'])} on '{s['track']}' has no original file: "
                            f"{s.get('path') or s.get('source')}",
                            "relink the project media (capcut_project.py link-originals) or pass --search <client folder>")

        # present: clips at their time and length, overlays at theirs
        if "present" in ran:
            for i in sorted(keep_c):
                c = clips[i]
                s = matched.get(i)
                label = f"clip {i + 1} {Path(c['file']).name} (planned {to_sf(c['at'])})"
                if s is None:
                    add("present", f"{label}: missing from the timeline (no segment with that source at src_in "
                        f"{to_sf(c['src_in'])})", "add the clip back or rebuild the timeline")
                    continue
                dt = s["at"] - c["at"]
                if abs(dt) > TOL:
                    add("present", f"{label}: {to_sf(abs(dt))} {'late' if dt > 0 else 'early'} (found at {to_sf(s['at'])})",
                        f"move it to {to_sf(c['at'])}")
                want = pt._clip_len(c)
                if abs(s["duration"] - want) > TOL:
                    add("present", f"{label}: length {to_sf(s['duration'])}, planned {to_sf(want)}",
                        f"trim it to {to_sf(want)}")
            for i in sorted(keep_o):
                o = overlays[i]
                s = matched_ov.get(i)
                label = f"overlay {i + 1} {o['template']} (planned {to_sf(o['at'])})"
                if s is None:
                    add("present", f"{label}: missing from the overlay tracks", "render and place the overlay")
                elif abs(s["duration"] - o["duration"]) > TOL:
                    add("present", f"{label}: length {to_sf(s['duration'])}, planned {to_sf(o['duration'])}",
                        f"set its length to {to_sf(o['duration'])}")

        # extras: video segments nobody planned
        if "extras" in ran:
            used = {id(s) for s in matched.values()} | {id(s) for s in matched_ov.values()}
            for s in by_kind["clip"] + by_kind["overlay"]:
                if id(s) not in used and in_window(s):
                    add("extras", f"unplanned segment on '{s['track']}' at {to_sf(s['at'])}, length "
                        f"{to_sf(s['duration'])}, {Path(str(s.get('source') or '?')).name}", "delete it, or add it to the plan")

        if "tracks_volumes" in ran:
            for i, s in matched.items():
                c = clips[i]
                label = f"clip {i + 1} {Path(c['file']).name}"
                if s["track"] != _expected_track(c):
                    add("tracks_volumes", f"{label} is on '{s['track']}', planned '{_expected_track(c)}'",
                        f"move it to '{_expected_track(c)}'")
                v = s.get("volume")
                if v is not None and abs(v - _expected_volume(c)) > 0.01:
                    add("tracks_volumes", f"{label} volume {v:g}, planned {_expected_volume(c):g}",
                        f"set its volume to {_expected_volume(c):g}")
            for key, want in (("vo", tl.get("vo_volume", 1.0)), ("music", tl.get("music_volume", 0.1))):
                if not tl.get(key):
                    continue
                track = [s for s in by_kind["audio"] if s["track"] == key]
                if not track:
                    add("tracks_volumes", f"no '{key}' track, but the plan has {key} {tl[key]}", f"add the {key}")
                for s in track:
                    if s.get("volume") is not None and abs(s["volume"] - want) > 0.01:
                        add("tracks_volumes", f"{key} volume {s['volume']:g}, planned {want:g}", f"set it to {want:g}")

        if "vo_span" in ran and tl.get("vo"):
            want = tl["vo_out"] - tl["vo_in"]
            vo = [s for s in by_kind["audio"] if s["track"] == "vo"]
            if not vo:
                add("vo_span", f"no 'vo' track for {tl['vo']}", "add the voice-over")
            for s in vo:
                if abs(s["at"]) > TOL or abs(s["duration"] - want) > TOL or abs((s.get("src_in") or 0.0) - tl["vo_in"]) > TOL:
                    add("vo_span", f"vo sits at {to_sf(s['at'])}, plays {to_sf(s.get('src_in') or 0)}-"
                        f"{to_sf((s.get('src_in') or 0) + s['duration'])} of the file; planned 0:00, "
                        f"{to_sf(tl['vo_in'])}-{to_sf(tl['vo_out'])}", "re-add the VO with the plan's vo_in/vo_out")
            edges = [("vo_in", tl["vo_in"])] if tl["vo_in"] > 0 else []
            try:
                vo_len = probe(tl["vo"])["duration"]
            except Exception:
                vo_len = None
            if vo_len is not None and tl["vo_out"] < vo_len - 1e-6:
                edges.append(("vo_out", tl["vo_out"]))
            for label, t in edges:
                if not silent(tl["vo"], t):
                    add("vo_span", f"{label} {to_sf(t)} is not silent (above -60 dB within the 0.8 s probe)",
                        "move it into the gap between words and rebuild")

        if "rotation" in ran:
            for i, s in matched.items():
                try:
                    info = probe(clips[i]["file"])
                except Exception:
                    continue
                if abs(info.get("rotation") or 0) % 180 == 90 and info.get("width") and info.get("height"):
                    upright = f"{info['height']}x{info['width']}"
                    if s.get("size") != upright:
                        add("rotation", f"clip {i + 1} {Path(clips[i]['file']).name} is rotated {info['rotation']} but "
                            f"stored as {s.get('size')}, upright is {upright}", "check the clip's orientation in CapCut")

        if "layout" in ran:
            for i, s in matched.items():
                c = clips[i]
                lay = c.get("layout")
                if not lay or c.get("keyframes"):
                    continue
                label = f"clip {i + 1} {Path(c['file']).name} ({lay})"
                tr, sc = s.get("transform") or {}, s.get("scale") or {}
                if lay in ("split-top", "split-bottom") and not s.get("mask"):
                    add("layout", f"{label} has no mask", "add the split mask (rectangle) in CapCut, or note it as manual")
                for axis in ("x", "y"):
                    if abs((tr.get(axis) or 0.0) - c.get(axis, 0.0)) > 0.02:
                        add("layout", f"{label} {axis} is {tr.get(axis)}, planned {c.get(axis, 0.0)}", f"set {axis} to {c.get(axis, 0.0)}")
                if abs((sc.get("x") or 1.0) - c.get("scale", 1.0)) > 0.02:
                    add("layout", f"{label} scale is {sc.get('x')}, planned {c.get('scale', 1.0)}", f"set scale to {c.get('scale', 1.0)}")

        cuts = [s["at"] for s in by_kind["clip"] if s["track"] == "video"]
        if "overlay_on_cut" in ran:
            for i in sorted(keep_o):
                s = matched_ov.get(i)
                if s is None or any(abs(s["at"] - t) <= CUT_TOL for t in cuts):
                    continue
                by_design = overlays[i].get("on") in ("word", "beat")
                add("overlay_on_cut", f"overlay {i + 1} {overlays[i]['template']} starts at {to_sf(s['at'])}, between cuts"
                    + (f" (planned on a {overlays[i]['on']})" if by_design else ""),
                    "move it to a cut" if not by_design else "check the start sits on the word or beat",
                    status="OPEN" if by_design else "FAIL")

        if "reuse" in ran:
            for j, s in enumerate(by_kind["clip"]):
                if s.get("source") is None:
                    continue
                idx = next((i for i, m in matched.items() if m is s), None)
                c = clips[idx] if idx is not None else {}
                entries.append((name, f"{name} {Path(str(s['source'])).name} at {to_sf(s['at'])}",
                                {"file": _norm(s["source"]), "src_in": s.get("src_in") or 0.0,
                                 "src_out": (s.get("src_in") or 0.0) + s["duration"] * (s.get("speed") or 1.0)},
                                bool(c.get("block") or c.get("shared")),
                                not delta or (idx is not None and idx in keep_c and _in_changed(changed, idx + 1, "c"))))

        if "dead_stretch" in ran:
            covers = [(s["at"], s["at"] + s["duration"]) for s in by_kind["overlay"] + by_kind["clip"] if s["track"] != "video"]
            end = dump.get("duration") or max((s["at"] + s["duration"] for s in by_kind["clip"]), default=0.0)
            points = sorted({0.0, end, *cuts, *(p for iv in covers for p in iv)})
            for a, b in zip(points, points[1:]):
                mid = (a + b) / 2
                if b - a > DEAD_S + 1e-6 and not any(x <= mid <= y for x, y in covers):
                    add("dead_stretch", f"{to_sf(a)}-{to_sf(b)} ({b - a:.1f} s) has no cut, overlay or B-roll",
                        "cut, add an overlay or punch in unless the line is a deliberate calm hold")

        if "talking_head_5s" in ran:
            above = [s for s in by_kind["overlay"] + by_kind["clip"] if s["track"] != "video"]
            for s in by_kind["clip"]:
                if s["track"] == "video" and s["duration"] > HEAD_S + 1e-6 and not any(
                        o["at"] < s["at"] + s["duration"] - 1e-6 and o["at"] + o["duration"] > s["at"] + 1e-6 for o in above):
                    add("talking_head_5s", f"{Path(str(s.get('source'))).name} runs {to_sf(s['duration'])} from {to_sf(s['at'])} "
                        "with no overlay or B-roll above it", "put B-roll or an overlay over it")

        if "sfx_repeat" in ran:
            sfx = sorted((s for s in by_kind["audio"] if str(s["track"]).startswith("sfx")), key=lambda s: s["at"])
            run, prev = 0, None
            for s in sfx:
                src = _norm(s.get("source"))
                run = run + 1 if src == prev else 1
                prev = src
                if run == 4:
                    add("sfx_repeat", f"{Path(str(s.get('source'))).name} plays more than 3 times in a row (4th at {to_sf(s['at'])})",
                        "swap in a different SFX for every third cue")

        if "music_level" in ran and tl.get("music"):
            v = tl.get("music_volume", 0.1)
            if not MUSIC_RANGE[0] <= v <= MUSIC_RANGE[1] and plan.get("style") != "product-ad" and not limits.get("product_ad"):
                add("music_level", f"music_volume {v:g} is outside {MUSIC_RANGE[0]}-{MUSIC_RANGE[1]} (about -20 dB under the VO)",
                    "check the level by ear or ebur128, or set it to 0.1")

        if "duration" in ran:
            d = dump.get("duration") or 0.0
            for key, bad, word in (("min_s", lambda: d < limits["min_s"] - 1e-6, "below the minimum"),
                                   ("max_s", lambda: d > limits["max_s"] + 1e-6, "above the maximum")):
                if limits.get(key) and bad():
                    add("duration", f"timeline runs {to_sf(d)} ({d:.2f} s), {word} {limits[key]} s", "retime to fit the brief")

        if "captions" in ran:
            for s in by_kind["text"]:
                if re.search(r"caption|subtitle", str(s["track"]), re.I):
                    add("captions", f"text on track '{s['track']}' at {to_sf(s['at'])}: {str(s.get('text'))[:40]!r}",
                        "delete the caption track; the user adds captions in CapCut")

    if "canvas" in ran:
        want = limits.get("canvas") or [1080, 1920]
        got = [plan.get("width", 1080), plan.get("height", 1920)]
        if abs(got[0] / got[1] - want[0] / want[1]) > 0.01:
            out.add("canvas", f"plan canvas is {got[0]}x{got[1]}, expected ratio {want[0]}:{want[1]}",
                    "set width/height in the plan and rebuild", "")

    if "reuse" in ran:
        for a in range(len(entries)):
            for b in range(a + 1, len(entries)):
                (ta, la, ca, xa, da), (tb, lb, cb, xb, db) = entries[a], entries[b]
                if (delta and not (da or db)) or (ta != tb and (xa or xb)) or not pt.source_overlaps(ca, cb):
                    continue
                out.add("reuse", f"{la} and {lb} use overlapping stretches of the same source "
                        f"({to_sf(max(ca['src_in'], cb['src_in']))}-{to_sf(min(ca['src_out'], cb['src_out']))})",
                        "use another take, or mark the clip shared", tb)

    failing = sum(r["status"] == "FAIL" for r in out.rows)
    bad = {r["check"] for r in out.rows}
    passed = len(ran - bad)
    prefix = "DELTA " if delta else ""
    verdict = f"{prefix}PASS" if not failing else f"{prefix}FAIL ({failing}{' issues' if not delta else ''})"
    return {"rows": out.rows, "passed": passed, "verdict": verdict}


def check_prompts_rows(spec: dict, script_lines: list[str], timings: dict | None) -> dict:
    """plan_tools.check_prompts as qa rows, so both CLI commands print one shape."""
    errs = pt.check_prompts(spec, script_lines, timings)
    rows = [{"n": i, "check": "prompts", "status": "FAIL", "evidence": e, "fix": "fix the prompt spec", "timeline": ""}
            for i, e in enumerate(errs, 1)]
    return {"rows": rows, "passed": 0 if errs else 1, "verdict": f"FAIL ({len(errs)} issues)" if errs else "PASS"}


def main(argv: list[str]) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")   # Windows consoles default to cp1252
    if not argv or argv[0] in ("-h", "--help"):
        raise SystemExit(__doc__)
    cmd, args = argv[0], argv[1:]

    def opt(k):
        return args[args.index(k) + 1] if k in args else None

    def load(path):
        return json.loads(Path(path).read_text(encoding="utf-8"))

    if cmd == "build":
        if len(args) < 2:
            raise SystemExit(__doc__)
        search = []
        for i, a in enumerate(args):
            if a == "--search":
                search += [x for x in args[i + 1:] if not x.startswith("--")]
        csv = lambda k: [x.strip() for x in opt(k).split(",") if x.strip()] if opt(k) else None   # noqa: E731
        res = check_build(load(args[0]), Path(args[1]), csv("--timelines"), csv("--changed"),
                          load(opt("--limits")) if opt("--limits") else None, search=search)
    elif cmd == "prompts":
        lines = [ln for ln in Path(opt("--script")).read_text(encoding="utf-8").splitlines() if ln.strip()] if opt("--script") else []
        res = check_prompts_rows(load(args[0]), lines, load(opt("--timings")) if opt("--timings") else None)
    else:
        raise SystemExit(f"unknown command {cmd!r}\n{__doc__}")
    print(json.dumps(res, indent=1, ensure_ascii=False))
    if "FAIL" in res["verdict"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
