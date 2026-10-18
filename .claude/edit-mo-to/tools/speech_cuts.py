"""Dead-air and mistake cuts for talking-head A-roll (avatars, creators, UGC hosts).

Silence and stutter/retake detection is ported from Herk Edit Kit's cut-silences and
cut-mistakes agents (MIT, Nate Herk, github.com/nateherkai/herk-edit-kit). Unlike the kit,
pauses are found from the audio itself, and every cut edge is snapped to the quietest
point nearby, because Whisper word times can be ~0.25s off and would clip consonants.

CLI (prints a short JSON summary; the full detail goes to the out file):
    propose <media> [--words vo.json] [--gap 0.55] [--breath S] [--out cuts.json]
        Transcribes (or takes `media_timing.py vo` JSON via --words), then writes every
        candidate cut: dead air (recommend cut) and stutters / false starts / retakes
        (recommend cut or review). Show the user the mistakes table before applying.
    apply <cuts.json> [--approve c003,c007] [--reject c001] [--script script.txt] [--out keep.json]
        Silence cuts and "recommend: cut" mistakes are applied unless rejected; "review"
        ones only if approved. Writes the keep segments (source in/out, timeline at and
        30 fps frames) and the words re-timed onto the cut timeline (plus line timings
        with --script), ready for the edit plan and vo_timings.
"""
import json
import re
import sys
from pathlib import Path

FPS = 30
HOP = 0.01  # RMS window, seconds
SR = 16000
MIN_KEEP = 0.04  # drop slivers shorter than this
STOP = set("a an and are as at be but by for from i if in is it of on or so that this to was we with you "
           "your they their there what when where why how like um uh".split())


# ---------- audio ----------
def rms_db(samples, sr: int = SR, hop: float = HOP):
    import numpy as np

    n = int(sr * hop)
    frames = len(samples) // n
    if frames == 0:
        return np.full(1, -120.0)
    x = np.asarray(samples[: frames * n], dtype=np.float64).reshape(frames, n)
    rms = np.sqrt((x ** 2).mean(axis=1))
    return 20 * np.log10(np.maximum(rms, 1e-6))


def silence_threshold(db) -> float:
    """10 dB over the room-tone floor, but never above -35 dBFS."""
    import numpy as np

    return float(min(np.percentile(db, 10) + 10.0, -35.0))


def silent_runs(db, thr: float, min_len: float, hop: float = HOP) -> list[tuple[float, float]]:
    runs, start = [], None
    for i, v in enumerate(list(db) + [0.0]):  # sentinel closes a trailing run
        if v < thr and start is None:
            start = i
        elif v >= thr and start is not None:
            if (i - start) * hop >= min_len:
                runs.append((start * hop, i * hop))
            start = None
    return runs


def snap_edge(db, t: float, window: float = 0.15, hop: float = HOP) -> float:
    """Move a cut edge to the quietest 10 ms within ±window (keeps consonants whole)."""
    import numpy as np

    i, w = int(round(t / hop)), int(round(window / hop))
    lo, hi = max(0, i - w), min(len(db), i + w + 1)
    if lo >= hi:
        return t
    return (lo + int(np.argmin(db[lo:hi]))) * hop


# ---------- words ----------
def _text(w: dict) -> str:
    return (w.get("word") if w.get("word") is not None else w.get("text")) or ""


def _token(text: str) -> str:
    return re.sub(r"^[^a-z0-9$%]+|[^a-z0-9$%]+$", "", text.lower())


def load_words(path: Path) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    words = data["words"] if isinstance(data, dict) else data
    return [{"word": _text(w).strip(), "start": float(w["start"]), "end": float(w["end"])}
            for w in words if (w.get("type") in (None, "word")) and w.get("start") is not None]


def _ends_sentence(words: list[dict], t: float, tol: float = 0.35) -> bool:
    before = [w for w in words if w["end"] <= t + tol]
    return bool(before) and bool(re.search(r"[.!?][\"')]*$", before[-1]["word"]))


def _context(words: list[dict], i: int, n: int = 6) -> str:
    return " ".join(w["word"] for w in words[max(0, i - n): i + n])


# ---------- detection ----------
def silence_cuts(words: list[dict], db, duration: float, gap: float = 0.55, head_pad: float = 0.22,
                 tail_pad: float = 0.34, breath: float | None = None, hop: float = HOP) -> list[dict]:
    """Pauses >= gap trimmed to a natural breath (0.24s after long pauses, 0.20s at sentence ends,
    0.14s otherwise, or `breath` for all); head/tail dead air trimmed to the pads."""
    thr = silence_threshold(db)
    cuts = []
    for a, b in silent_runs(db, thr, gap, hop):
        if a <= hop:  # head
            if b - head_pad > a:
                cuts.append({"type": "head", "cut": [0.0, b - head_pad], "note": f"dead air before speech {b:.2f}s"})
            continue
        if b >= duration - hop:  # tail
            if a + tail_pad < duration:
                cuts.append({"type": "tail", "cut": [a + tail_pad, duration], "note": f"dead air after speech {duration - a:.2f}s"})
            continue
        length = b - a
        keep = breath if breath is not None else 0.24 if length >= 2 else 0.20 if _ends_sentence(words, a) else 0.14
        start, end = a + keep * 0.55, b - keep * 0.45  # breath biased to the end of the phrase
        if end - start >= MIN_KEEP:
            cuts.append({"type": "pause", "cut": [start, end], "note": f"pause {length:.2f}s -> {keep:.2f}s"})
    for c in cuts:
        c["recommend"] = "cut"
    return cuts


def _segments(words: list[dict]) -> list[dict]:
    segs, s = [], 0
    for i in range(1, len(words) + 1):
        if i < len(words):
            prev, cur = words[i - 1], words[i]
            elapsed = cur["end"] - words[s]["start"]
            if not (cur["start"] - prev["end"] > 0.85 or (re.search(r"[.!?]$", prev["word"]) and elapsed >= 7.5) or elapsed >= 16):
                continue
        segs.append({"w0": s, "w1": i - 1, "start": words[s]["start"], "end": words[i - 1]["end"],
                     "text": " ".join(w["word"] for w in words[s:i])})
        s = i
    return segs


def _signature(text: str) -> list[str]:
    toks = re.sub(r"[^a-z0-9\s$%]", " ", text.lower()).split()
    return [t for t in toks if len(t) > 2 and t not in STOP][:18]


def _jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    return len(sa & sb) / max(1, len(sa | sb))


def mistake_cuts(words: list[dict]) -> list[dict]:
    """Stutters (immediate repeats), false starts and retakes. Mechanical: always review in context,
    because emphasis ("never, never") looks like a stutter."""
    out = []
    for i in range(1, len(words)):
        a, b = words[i - 1], words[i]
        ta, tb = _token(a["word"]), _token(b["word"])
        if tb and ta == tb and b["start"] - a["end"] < 0.5:
            out.append({"type": "stutter", "cut": [a["start"], b["start"]], "recommend": "cut",
                        "removes": a["word"], "keeps": b["word"], "context": _context(words, i),
                        "note": f'repeated "{ta}"'})
    segs = _segments(words)
    sigs = [_signature(s["text"]) for s in segs]
    for i in range(len(segs)):
        for j in range(i + 1, min(len(segs), i + 9)):
            if segs[j]["start"] - segs[i]["end"] > 75:
                break
            score = _jaccard(sigs[i], sigs[j])
            same_open = sum(1 for k, t in enumerate(sigs[i][:4]) if k < len(sigs[j]) and sigs[j][k] == t) >= 2
            if score >= 0.34 or (score >= 0.24 and same_open):
                false_start = same_open and segs[i]["end"] - segs[i]["start"] < 6 and segs[j]["start"] - segs[i]["end"] < 12
                out.append({"type": "false_start" if false_start else "retake",
                            "cut": [segs[i]["start"], segs[j]["start"]],
                            "recommend": "cut" if score >= 0.34 else "review", "score": round(score, 2),
                            "removes": segs[i]["text"], "keeps": segs[j]["text"],
                            "note": f"take {i + 1} ~ take {j + 1} (similarity {score:.2f}{', same opening' if same_open else ''})"})
    return out


# ---------- applying ----------
def merge(ranges: list[list[float]]) -> list[list[float]]:
    out = []
    for a, b in sorted(r for r in ranges if r[1] > r[0]):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def keep_segments(duration: float, cuts: list[list[float]], fps: int = FPS) -> list[dict]:
    """Complement of the cuts, each kept length rounded to whole frames so clips sit back to back
    on the timeline (integer frame starts, no gaps or overlaps)."""
    keeps, cursor = [], 0.0
    for a, b in merge(cuts):
        if a > cursor:
            keeps.append((cursor, a))
        cursor = max(cursor, b)
    if cursor < duration:
        keeps.append((cursor, duration))
    out, frame = [], 0
    for a, b in keeps:
        n = round((b - a) * fps)
        if n < max(1, round(MIN_KEEP * fps)):
            continue
        out.append({"src_in": round(a, 4), "src_out": round(a + n / fps, 4),
                    "at": round(frame / fps, 10), "from_frame": frame, "to_frame": frame + n})
        frame += n
    return out


def retime(words: list[dict], segs: list[dict]) -> list[dict]:
    """Words onto the cut timeline; words that fall in a cut are dropped."""
    out = []
    for w in words:
        mid = (w["start"] + w["end"]) / 2
        for s in segs:
            if s["src_in"] <= mid < s["src_out"]:
                shift = s["at"] - s["src_in"]
                out.append({**w, "start": round(max(s["at"], w["start"] + shift), 3),
                            "end": round(min(s["at"] + s["src_out"] - s["src_in"], w["end"] + shift), 3)})
                break
    return out


def propose(media: Path, words: list[dict], samples, gap: float = 0.55, breath: float | None = None) -> dict:
    db = rms_db(samples)
    duration = len(samples) / SR
    cands = silence_cuts(words, db, duration, gap=gap, breath=breath) + mistake_cuts(words)
    for c in cands:
        if c["type"] not in ("pause", "head", "tail"):  # silence cut edges already sit in silence
            c["cut"] = [snap_edge(db, c["cut"][0]), snap_edge(db, c["cut"][1])]
        c["cut"] = [round(c["cut"][0], 3), round(c["cut"][1], 3)]
    cands = [c for c in cands if c["cut"][1] - c["cut"][0] >= MIN_KEEP]
    cands.sort(key=lambda c: c["cut"][0])
    for n, c in enumerate(cands, 1):
        c["id"] = f"c{n:03d}"
    return {"media": str(media), "duration": round(duration, 3), "words": words, "candidates": cands}


def apply(data: dict, approve: set[str], reject: set[str], fps: int = FPS) -> dict:
    chosen = [c for c in data["candidates"]
              if c["id"] not in reject and (c["recommend"] == "cut" or c["id"] in approve)]
    segs = keep_segments(data["duration"], [c["cut"] for c in chosen], fps)
    total = segs[-1]["to_frame"] / fps if segs else 0.0
    return {"media": data["media"], "applied": [c["id"] for c in chosen],
            "source_duration": data["duration"], "cut_duration": round(total, 3),
            "removed": round(data["duration"] - total, 3), "segs": segs,
            "words": retime(data["words"], segs)}


def _opt(argv: list[str], name: str, default=None):
    if name in argv:
        i = argv.index(name)
        val = argv[i + 1]
        del argv[i:i + 2]
        return val
    return default


def main(argv: list[str]) -> None:
    from media_timing import _load_16k, align_lines, to_sf, transcribe

    argv = list(argv)
    cmd = argv.pop(0)
    if cmd == "propose":
        words_file, out = _opt(argv, "--words"), _opt(argv, "--out")
        gap, breath = float(_opt(argv, "--gap", 0.55)), _opt(argv, "--breath")
        media = Path(argv[0])
        samples = _load_16k(media)
        words = load_words(Path(words_file)) if words_file else transcribe(media)
        data = propose(media, words, samples, gap=gap, breath=float(breath) if breath else None)
        out = Path(out or media.with_suffix(".cuts.json"))
        out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        silence = [c for c in data["candidates"] if c["type"] in ("pause", "head", "tail")]
        mistakes = [{"id": c["id"], "type": c["type"], "recommend": c["recommend"],
                     "cut": f'{to_sf(c["cut"][0])}–{to_sf(c["cut"][1])}', "removes": c["removes"][:90],
                     "keeps": c["keeps"][:60]} for c in data["candidates"] if c not in silence]
        print(json.dumps({"out": str(out), "duration": to_sf(data["duration"]),
                          "silence_cuts": len(silence), "silence_seconds": round(sum(c["cut"][1] - c["cut"][0] for c in silence), 2),
                          "mistakes": mistakes}, ensure_ascii=False, indent=1))
    elif cmd == "apply":
        approve = set(filter(None, (_opt(argv, "--approve", "") or "").split(",")))
        reject = set(filter(None, (_opt(argv, "--reject", "") or "").split(",")))
        script, out = _opt(argv, "--script"), _opt(argv, "--out")
        src = Path(argv[0])
        res = apply(json.loads(src.read_text(encoding="utf-8")), approve, reject)
        if script:
            lines = [l.strip() for l in Path(script).read_text(encoding="utf-8").splitlines() if l.strip()]
            res["lines"] = align_lines(res["words"], lines)
        out = Path(out or src.with_name(src.name.replace(".cuts.json", ".keep.json")))
        out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps({"out": str(out), "segments": len(res["segs"]), "applied": len(res["applied"]),
                          "source": to_sf(res["source_duration"]), "cut": to_sf(res["cut_duration"]),
                          "removed": to_sf(res["removed"])}, indent=1))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main(sys.argv[1:])
