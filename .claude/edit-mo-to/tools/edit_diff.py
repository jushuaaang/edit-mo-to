"""Learn how the editor edits: compare a timeline as we built it with how the editor finished it in CapCut.

CLI (prints JSON):
    snapshot <project> <timeline> <out.json> [client folder ...]
        Right after a build or revision: save the timeline as built (the editor agent does this).
    diff <built.json> <project> <timeline> [client folder ...] [--log patterns.jsonl --video <name>]
        At the learning step: every hand edit (trimmed, moved, removed, added, volume, speed, reframed)
        plus plain-language patterns with counts. With --log, the patterns are appended to the
        cross-video log, and `recurring` lists patterns seen in 2+ videos (strong rule candidates).
    history [patterns.jsonl]
        Patterns that recur across videos.

Caption text segments the editor adds are counted, never treated as a style change (captions are theirs).
"""
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

FPS = 30
TOL = 1.5 / FPS  # changes under ~1.5 frames are rounding, not edits


def sf(seconds: float) -> str:
    frames = round(abs(seconds) * FPS)
    s, f = divmod(frames, FPS)
    return f"{'-' if seconds < 0 else ''}{s}:{f:02d}"


def kind(seg: dict) -> str:
    track = (seg.get("track") or "").lower()
    src = (seg.get("source") or seg.get("path") or "").lower().replace("\\", "/")
    if seg.get("track_type") == "text" or seg.get("material_type") == "texts":
        return "text"
    if seg.get("track_type") == "audio":
        if "vo" == track or track.startswith("vo"):
            return "vo"
        if "music" in track:
            return "music"
        return "sfx" if "sfx" in track or "/sfx/" in src else "audio"
    if "cutout" in track:
        return "cutout"
    if track.startswith("overlay") or "/motion/" in src:
        return "overlay"
    if track in ("video", "video_main", "main"):
        return "a-roll"
    return "b-roll"


def _scale(seg):
    s = seg.get("scale") or {}
    return float(s.get("x", 1.0)) if isinstance(s, dict) else 1.0


def _pos(seg):
    t = seg.get("transform") or {}
    return (float(t.get("x", 0.0)), float(t.get("y", 0.0))) if isinstance(t, dict) else (0.0, 0.0)


def _key(seg):
    return (kind(seg), seg.get("source") or seg.get("text") or seg.get("path"))


def match(built: list[dict], final: list[dict]) -> tuple[list[tuple[dict, dict]], list[dict], list[dict]]:
    """Pair segments by (kind, source), nearest timeline position first."""
    pool = defaultdict(list)
    for s in final:
        pool[_key(s)].append(s)
    pairs, removed = [], []
    for b in sorted(built, key=lambda s: s["at"]):
        cands = pool.get(_key(b)) or []
        if not cands:
            removed.append(b)
            continue
        best = min(cands, key=lambda f: abs(f["at"] - b["at"]) + abs((f.get("src_in") or 0) - (b.get("src_in") or 0)))
        cands.remove(best)
        pairs.append((b, best))
    added = [s for v in pool.values() for s in v]
    return pairs, removed, added


def _cuts(final: list[dict]) -> list[float]:
    """Timeline times where a picture clip starts or ends (A-roll and B-roll)."""
    out = set()
    for s in final:
        if kind(s) in ("a-roll", "b-roll"):
            out.update((round(s["at"], 3), round(s["at"] + s["duration"], 3)))
    return sorted(out)


def _on_cut(t: float, cuts: list[float]) -> bool:
    return any(abs(t - c) <= TOL for c in cuts)


def diff(built: dict, final: dict) -> dict:
    b_segs, f_segs = built["segments"], final["segments"]
    pairs, removed, added = match(b_segs, f_segs)
    cuts = _cuts(f_segs)
    changes = []
    for b, f in pairs:
        k, ch = kind(b), {}
        if abs(f["at"] - b["at"]) > TOL:
            ch["moved"] = round(f["at"] - b["at"], 3)
        if abs(f["duration"] - b["duration"]) > TOL:
            ch["length"] = round(f["duration"] - b["duration"], 3)
        if b.get("src_in") is not None and f.get("src_in") is not None and abs(f["src_in"] - b["src_in"]) > TOL:
            ch["src_in"] = round(f["src_in"] - b["src_in"], 3)
        vb, vf = b.get("volume"), f.get("volume")
        if vb is not None and vf is not None and abs(vf - vb) > 0.01:
            ch["volume_db"] = round(20 * math.log10(max(vf, 1e-4) / max(vb, 1e-4)), 1)
        if (b.get("speed") or 1) != (f.get("speed") or 1):
            ch["speed"] = [b.get("speed") or 1, f.get("speed") or 1]
        if abs(_scale(f) - _scale(b)) > 0.01:
            ch["scale"] = [round(_scale(b), 3), round(_scale(f), 3)]
        if max(abs(x - y) for x, y in zip(_pos(f), _pos(b))) > 0.01:
            ch["position"] = [_pos(b), _pos(f)]
        if (b.get("track") or "") != (f.get("track") or ""):
            ch["track"] = [b.get("track"), f.get("track")]
        if ch:
            if "moved" in ch and k in ("overlay", "sfx"):
                ch["now_on_cut"], ch["was_on_cut"] = _on_cut(f["at"], cuts), _on_cut(b["at"], cuts)
            changes.append({"kind": k, "file": Path(b.get("source") or b.get("path") or "").name or b.get("text"),
                            "at": sf(b["at"]), **ch})
    captions = [s for s in added if kind(s) == "text"]
    added = [s for s in added if kind(s) != "text"]
    return {"timeline": final.get("timeline"), "duration_built": sf(built.get("duration", 0)),
            "duration_final": sf(final.get("duration", 0)), "changed": changes,
            "removed": [{"kind": kind(s), "file": Path(s.get("source") or s.get("path") or "").name, "at": sf(s["at"]),
                         "length": sf(s["duration"])} for s in removed],
            "added": [{"kind": kind(s), "file": Path(s.get("source") or s.get("path") or "").name, "at": sf(s["at"]),
                       "length": sf(s["duration"])} for s in added],
            "caption_segments_added": len(captions),
            "patterns": patterns(pairs, changes, removed, added, b_segs)}


def patterns(pairs, changes, removed, added, built) -> list[dict]:
    """Plain-language habits, each with a stable id (to count it across videos) and its evidence."""
    total = Counter(kind(s) for s in built)
    out = []

    def add(pid, text, n):
        out.append({"id": pid, "text": text, "count": n})

    for k in ("a-roll", "b-roll", "overlay", "music", "sfx", "vo"):
        lens = [c["length"] for c in changes if c["kind"] == k and "length" in c]
        if lens:
            shorter = [x for x in lens if x < 0]
            if len(shorter) >= max(2, len(lens) * 0.6):
                add(f"{k}:shorter", f"Shortened {len(shorter)} of {total[k]} {k} clips, by {sf(-sum(shorter) / len(shorter))} on average", len(shorter))
            longer = [x for x in lens if x > 0]
            if len(longer) >= max(2, len(lens) * 0.6):
                add(f"{k}:longer", f"Lengthened {len(longer)} of {total[k]} {k} clips, by {sf(sum(longer) / len(longer))} on average", len(longer))
        moves = [c for c in changes if c["kind"] == k and "moved" in c]
        if len(moves) >= 2:
            to_cut = sum(1 for c in moves if c.get("now_on_cut") and not c.get("was_on_cut"))
            if k in ("overlay", "sfx") and to_cut >= 2:
                add(f"{k}:to-cut", f"Moved {to_cut} {k} items onto a video cut", to_cut)
            early = [c["moved"] for c in moves if c["moved"] < 0]
            late = [c["moved"] for c in moves if c["moved"] > 0]
            if len(early) >= max(2, len(moves) * 0.6):
                add(f"{k}:earlier", f"Moved {len(early)} {k} items earlier, by {sf(-sum(early) / len(early))} on average", len(early))
            if len(late) >= max(2, len(moves) * 0.6):
                add(f"{k}:later", f"Moved {len(late)} {k} items later, by {sf(sum(late) / len(late))} on average", len(late))
        vols = [c["volume_db"] for c in changes if c["kind"] == k and "volume_db" in c]
        if vols and (k in ("music", "sfx", "vo") or len(vols) >= 2):
            avg = sum(vols) / len(vols)
            add(f"{k}:{'louder' if avg > 0 else 'quieter'}", f"Made {k} {'louder' if avg > 0 else 'quieter'} by {abs(avg):.1f} dB ({len(vols)} clips)", len(vols))
        scales = [c["scale"] for c in changes if c["kind"] == k and "scale" in c]
        if len(scales) >= 2:
            up = sum(1 for a, b in scales if b > a)
            add(f"{k}:{'zoom-in' if up * 2 >= len(scales) else 'zoom-out'}",
                f"Re-scaled {len(scales)} {k} clips ({up} bigger, {len(scales) - up} smaller)", len(scales))
        if sum(1 for c in changes if c["kind"] == k and "position" in c) >= 2:
            n = sum(1 for c in changes if c["kind"] == k and "position" in c)
            add(f"{k}:reframed", f"Re-positioned {n} {k} clips", n)
        if sum(1 for c in changes if c["kind"] == k and "speed" in c) >= 1:
            n = sum(1 for c in changes if c["kind"] == k and "speed" in c)
            add(f"{k}:speed", f"Changed the speed of {n} {k} clips", n)
    for k, n in Counter(kind(s) for s in removed).items():
        if n >= 2 or (k == "overlay" and n >= 1):
            add(f"{k}:removed", f"Deleted {n} of {total[k]} {k} items", n)
    for k, n in Counter(kind(s) for s in added).items():
        if n >= 1:
            add(f"{k}:added", f"Added {n} {k} items of their own", n)
    return out


def recurring(log: Path, min_videos: int = 2) -> list[dict]:
    if not log.exists():
        return []
    seen = defaultdict(list)
    for line in log.read_text(encoding="utf-8").splitlines():
        if line.strip():
            e = json.loads(line)
            for p in e.get("patterns", []):
                seen[p["id"]].append({"video": e.get("video"), "text": p["text"]})
    return [{"id": k, "videos": len({x["video"] for x in v}), "examples": [x["text"] for x in v[-3:]]}
            for k, v in sorted(seen.items(), key=lambda kv: -len(kv[1]))
            if len({x["video"] for x in v}) >= min_videos]


def _opt(argv, name):
    if name in argv:
        i = argv.index(name)
        v = argv[i + 1]
        del argv[i:i + 2]
        return v
    return None


def main(argv: list[str]) -> None:
    argv = list(argv)
    cmd = argv.pop(0) if argv else ""
    if cmd == "snapshot":
        from capcut_project import segments

        project, timeline, out = argv[0], argv[1], Path(argv[2])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(segments(Path(project), timeline, [Path(p) for p in argv[3:]]), ensure_ascii=False),
                       encoding="utf-8")
        res = {"saved": str(out)}
    elif cmd == "diff":
        from capcut_project import segments

        log, video = _opt(argv, "--log"), _opt(argv, "--video")
        built = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
        final = segments(Path(argv[1]), argv[2], [Path(p) for p in argv[3:]])
        res = diff(built, final)
        if log:
            Path(log).parent.mkdir(parents=True, exist_ok=True)
            with open(log, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"video": video or argv[1], "timeline": argv[2],
                                     "patterns": res["patterns"]}, ensure_ascii=False) + "\n")
            res["recurring"] = recurring(Path(log))
        res["changed"] = res["changed"][:40]  # keep the hand-back small; patterns carry the summary
    elif cmd == "history":
        res = recurring(Path(argv[0]) if argv else Path(__file__).resolve().parents[1] / "edit-patterns.jsonl")
    else:
        raise SystemExit(__doc__)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main(sys.argv[1:])
