"""Mechanical build QA: every build-gate check of qa.md that needs no eyes, reporting only failures.

CLI (prints JSON {"rows": [...], "passed": N, "verdict": ...}; exit code 1 on a FAIL verdict):
    build <plan.json> "<project>" [--timelines "A,B"] [--changed 3,7,ov2] [--limits limits.json] [--search dir ...]
                         clips/overlays present at their time and length, extras, tracks and volumes, VO span and
                         edges, rotation, layout, overlays on cuts, reuse, dead stretches, talking head > 5 s,
                         SFX repeats, music level, duration, canvas, captions, unknown sources.
                         --changed limits present/extras/overlay_on_cut/reuse to those clips (numbers) and
                         overlays (ovN) and their neighbours, and prefixes the verdict with DELTA
    captions <plan.json> "<project>" "<timeline>" [--script s.txt] [--timings vo.json] [--limits limits.json] [--vo-track NAME] [--search dir ...]
                         Claude's `captions` text track against the script and the timeline's live VO: caption_words,
                         caption_sync, caption_band, caption_gaps (--script / --timings default to the plan's captions.*)
    prompts <prompts2.json> [--script script.txt] [--timings t.json]
                         plan_tools.check_prompts, as the same row format
Rows are FAIL (counts toward the verdict) or OPEN (for the user to look at). `passed` counts the checks that ran
and produced no rows.
"""
import difflib
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
OPEN_CHECKS = {"rotation", "dead_stretch", "music_level", "temp_en", "caption_gaps"}   # advisory: the user looks, the verdict ignores them
TEMP_EN_TRACK = "TEMP_EN_delete_me"   # build_project's temporary English review track
CAPTIONS_TRACK = "captions"           # build_project's step-10 caption track
GAP_S = 0.5
B_ROLL_TRACKS = {"video_top", "video_bottom", "video_overlay"}


def _norm(path) -> str:
    p = pt.mr.plain_path(path)
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


CUTOUT_TRACK = "overlay_cutout"


def _match_cutouts(overlays: list[dict], segs: list[dict]) -> dict[int, dict]:
    """Overlay index -> its cutout segment (the person cut out above a `cutout: true` overlay), matched on the
    cutout file, else on the overlay's start."""
    used, out = set(), {}
    for i, o in enumerate(overlays):
        if not o.get("cutout"):
            continue
        cands = [j for j, s in enumerate(segs) if j not in used and o.get("cutout_file") and s.get("source")
                 and _norm(s["source"]) == _norm(o["cutout_file"])]
        cands = cands or [j for j, s in enumerate(segs) if j not in used and abs(s["at"] - o["at"]) <= TOL]
        if cands:
            j = min(cands, key=lambda j: abs(segs[j]["at"] - o["at"]))
            used.add(j)
            out[i] = segs[j]
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


def _words_of(text) -> list[str]:
    """Comparable tokens: case-folded, punctuation dropped."""
    return [w for w in re.sub(r"[^\w\s]|_", "", str(text or "").casefold()).split() if w]


def check_captions(plan: dict, project: Path, timeline: str, script_lines: list[str], words: list[dict],
                   limits: dict | None = None, segments_fn=None, search=(), vo_track: str | None = None) -> dict:
    """Claude's `captions` track on one timeline against the script words that survive the timeline's live VO."""
    import captions as cap
    segments_fn = segments_fn or cp.segments
    limits = limits or {}
    out = _Rows()
    names = [tl["name"] for tl in plan.get("timelines", [])]
    if timeline not in names:
        raise ValueError(f"unknown timeline {timeline!r}; the plan has {names}")
    dump = segments_fn(project, timeline, list(search))
    caps = sorted((s for s in dump.get("segments", []) if _kind(s) == "text" and s["track"] == CAPTIONS_TRACK),
                  key=lambda s: s["at"])
    tl = next(t for t in plan["timelines"] if t["name"] == timeline)
    kept, dropped = cap.to_timeline(cap.script_words(words, script_lines), dump, vo_in=tl.get("vo_in", 0.0), vo_track=vo_track)
    want = [t for w in kept for t in _words_of(w["word"])]
    got = [t for s in caps for t in _words_of(s.get("text"))]
    add = lambda check, ev, fix, status=None: out.add(check, ev, fix, timeline, status)   # noqa: E731

    if not caps:
        add("caption_words", f"no text on the '{CAPTIONS_TRACK}' track", "run build_project.py captions for this timeline")
    elif got != want:
        sm = difflib.SequenceMatcher(a=want, b=got, autojunk=False)
        diffs = [f"{' '.join(want[a0:a1]) or '-'} -> {' '.join(got[b0:b1]) or '-'}"
                 for op, a0, a1, b0, b1 in sm.get_opcodes() if op != "equal"]
        add("caption_words", f"captions differ from the script (script -> caption): {'; '.join(diffs[:6])}",
            "rerun build_project.py captions, or fix the caption text to the script")
    if dropped:
        listed = ", ".join(repr(w["word"]) for w in dropped[:12])
        add("caption_words", f"{len(dropped)} script word(s) not in the timeline's VO, so not captioned: {listed}",
            "check these words are meant to be cut", status="OPEN")

    # sync: walk the captions over the kept words in order; a caption starts with its first word and lasts to its last
    i = 0
    for s in caps:
        take, cnt, n = [], 0, len(_words_of(s.get("text")))
        while cnt < n and i < len(kept):
            k = len(_words_of(kept[i]["word"]))   # a bare symbol ("-", "&") has no token and no caption of its own
            if k:
                take.append(kept[i])
                cnt += k
            i += 1
        if not take:
            break
        t0, t1 = take[0]["start"], take[-1]["end"]
        if abs(s["at"] - t0) > TOL or s["at"] + s["duration"] < t1 - TOL:
            add("caption_sync", f"caption {str(s.get('text'))[:30]!r} runs {to_sf(s['at'])}-{to_sf(s['at'] + s['duration'])} "
                f"but its words are spoken {to_sf(t0)}-{to_sf(t1)}", "retime the caption to its words (rerun build_project.py captions)")

    # band: the bottom `caption_band_px` of the canvas (y in half-canvas units, -1 = bottom edge)
    top = -1 + 2 * float(limits.get("caption_band_px", 400)) / pt.canvas(plan)[1]
    for s in caps:
        y = (s.get("transform") or {}).get("y", 0.0)
        if not -1 - 1e-6 <= y <= top + 1e-6:
            add("caption_band", f"caption {str(s.get('text'))[:30]!r} at y={y:g} is outside the bottom band (y from -1 to {top:.2f})",
                "move the captions into the bottom band (captions_style transform_y)")
            break

    # gaps: speech with no caption over it for more than GAP_S
    edges = [(0.0, 0.0)] + [(s["at"], s["at"] + s["duration"]) for s in caps] + [(1e9, 1e9)]
    for (_, gap0), (gap1, _) in zip(edges, edges[1:]):
        if gap1 - gap0 > GAP_S:
            spoken = [w for w in kept if w["start"] >= gap0 - 1e-6 and w["end"] <= gap1 + 1e-6]
            if spoken:
                add("caption_gaps", f"no caption {to_sf(gap0)}-{to_sf(spoken[-1]['end'])} while "
                    f"{' '.join(w['word'] for w in spoken[:6])!r} is spoken", "caption the missing words", status="OPEN")
    fails = [r for r in out.rows if r["status"] == "FAIL"]
    return {"rows": out.rows, "passed": 4 - len({r["check"] for r in out.rows}),
            "verdict": f"FAIL ({len(fails)} issues)" if fails else "PASS"}


def check_build(plan: dict, project: Path, timelines: list[str] | None = None, changed: list[str] | None = None,
                limits: dict | None = None, segments_fn=None, probe=None, silent=None, search=()) -> dict:
    segments_fn = segments_fn or cp.segments
    probe = probe or pt.probe_media
    silent = silent or pt.edge_silent
    limits = limits or {}
    delta = changed is not None
    out = _Rows()
    names = [tl["name"] for tl in plan.get("timelines", [])]
    unknown = [n for n in timelines or [] if n not in names]
    if unknown:   # filtering to nothing would PASS with every check "passed"
        raise ValueError(f"unknown timeline(s) {unknown}; the plan has {names}. A revise-new-timeline timeline is "
                         f"checked on its built plan copy <base>/.edit-mo-to/built/<new name>.plan.json")
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
        try:
            dump = segments_fn(project, name, list(search))
        except KeyError as e:
            out.add("present", f"timeline '{name}' is not in the project: {e.args[0] if e.args else e}",
                    "build it, or run qa_check on the plan that names it as the project does "
                    "(after revise-new-timeline: <base>/.edit-mo-to/built/<new name>.plan.json)", name, "FAIL")
            continue
        segs = dump.get("segments", [])
        by_kind = {k: [s for s in segs if _kind(s) == k] for k in ("clip", "overlay", "audio", "text")}
        matched = _match_clips(clips, by_kind["clip"])
        cut_segs = [s for s in by_kind["overlay"] if s["track"] == CUTOUT_TRACK]
        matched_ov = _match_overlays(overlays, [s for s in by_kind["overlay"] if s["track"] != CUTOUT_TRACK])
        matched_cut = _match_cutouts(overlays, cut_segs)

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
                if o.get("cutout") and i not in matched_cut:
                    add("present", f"{label}: its cutout (the person above it) is missing from '{CUTOUT_TRACK}'",
                        "rebuild the timeline, or place the cutout_file over the overlay")
                if s is None:
                    add("present", f"{label}: missing from the overlay tracks", "render and place the overlay")
                elif abs(s["duration"] - o["duration"]) > TOL:
                    add("present", f"{label}: length {to_sf(s['duration'])}, planned {to_sf(o['duration'])}",
                        f"set its length to {to_sf(o['duration'])}")

        # extras: video segments nobody planned
        if "extras" in ran:
            used = {id(s) for m in (matched, matched_ov, matched_cut) for s in m.values()}
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
                if s["track"] != TEMP_EN_TRACK and re.search(r"caption|subtitle", str(s["track"]), re.I):
                    add("captions", f"text on track '{s['track']}' at {to_sf(s['at'])}: {str(s.get('text'))[:40]!r}",
                        "delete the caption track; the user adds captions in CapCut")
            if any(s["track"] == TEMP_EN_TRACK for s in by_kind["text"]):
                add("temp_en", "TEMP_EN present (delete before export)",
                    f"delete the {TEMP_EN_TRACK} track in CapCut before the export", status="OPEN")

    if "canvas" in ran:
        # the brief's ratio (limits.json `ratio`, or an explicit `canvas`), else the 9:16 default
        want = limits.get("canvas") or pt.ratio(limits.get("ratio")) or (9, 16)
        got = pt.canvas(plan)
        if abs(got[0] / got[1] - want[0] / want[1]) > 0.01:
            out.add("canvas", f"plan canvas is {got[0]}x{got[1]}, expected ratio {want[0]:g}:{want[1]:g}",
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
            if a == "--search":   # its folders run up to the next option
                for x in args[i + 1:]:
                    if x.startswith("--"):
                        break
                    search.append(x)
        csv = lambda k: [x.strip() for x in opt(k).split(",") if x.strip()] if opt(k) else None   # noqa: E731
        try:
            res = check_build(load(args[0]), Path(args[1]), csv("--timelines"), csv("--changed"),
                              load(opt("--limits")) if opt("--limits") else None, search=search)
        except ValueError as e:
            raise SystemExit(f"qa_check: {e}")
    elif cmd == "captions":
        if len(args) < 3:
            raise SystemExit(__doc__)
        plan = load(args[0])
        c = plan.get("captions") or {}
        script, timings = opt("--script") or c.get("script"), opt("--timings") or c.get("timings")
        if not script or not timings:
            raise SystemExit("qa_check: captions needs --script and --timings (or the plan's captions.script / captions.timings)")
        import captions as cap
        search = []
        for i, a in enumerate(args):
            if a == "--search":
                for x in args[i + 1:]:
                    if x.startswith("--"):
                        break
                    search.append(x)
        try:
            res = check_captions(plan, Path(args[1]), args[2], cap._lines(script), json.loads(cap._read(timings)).get("words", []),
                                 load(opt("--limits")) if opt("--limits") else None, search=search, vo_track=opt("--vo-track"))
        except ValueError as e:
            raise SystemExit(f"qa_check: {e}")
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
