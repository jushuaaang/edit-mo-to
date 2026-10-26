"""Caption chunks from the script + VO word timings, timed through the timeline; temporary English rows.

The chunking mirrors the ugc-captions template (cut at punctuation and pauses first, then max words;
no one-word orphan; numbers stay with the next word, % with the number; short chunks merge), without
its Italian function-word costs. The script is the source of truth for the words; ASR gives the times.

CLI (prints JSON):
    chunks <vo.json> <script.txt> <project> "<timeline>" [--max-words 4] --out chunks.json
                                         script words timed by the VO, mapped onto the timeline through
                                         its VO segments (words cut from the VO are dropped), chunked
    temp-en <vo.json> <script_en.txt> --out rows.json
                                         one temporary English row per script line (VO-file time)
"""
import json
import re
import sys
from pathlib import Path

import capcut_project
from media_timing import _tokens

HARD = re.compile(r"[.!?:…][\"»”']?$")
SOFT = re.compile(r"[,;—–][\"»”']?$")
NUM = re.compile(r"^\d+([.,]\d+)?$")
LONG_PAUSE = 0.6   # a gap up to this keeps the chunk on screen until the next one
LINGER = 0.3       # otherwise it stays this long after its last word
MIN_SHOWN = 0.5    # a chunk on screen for less merges with a neighbour


def _norm(word: str) -> str:
    return "".join(_tokens(word))


def script_words(words: list[dict], script_lines: list[str]) -> list[dict]:
    """The script's words with the ASR times, by character-level edit-distance alignment."""
    st = []
    for li, line in enumerate(script_lines):
        st += [{"word": t, "line": li} for t in line.split()]
    asr = [w for w in words if str(w.get("word", "")).strip()]
    A, a_tok, B, b_tok = [], [], [], []
    for i, t in enumerate(st):
        for c in _norm(t["word"]):
            A.append(c)
            a_tok.append(i)
    for i, w in enumerate(asr):
        for c in _norm(str(w["word"])):
            B.append(c)
            b_tok.append(i)
    n, m = len(A), len(B)
    # dir: 0 diagonal, 1 up (script char unmatched), 2 left (ASR char unmatched)
    dirs = [bytearray(m + 1) for _ in range(n + 1)]
    for j in range(m + 1):
        dirs[0][j] = 2
    prev = list(range(m + 1))
    for i in range(1, n + 1):
        cur = [i] + [0] * m
        dirs[i][0] = 1
        ai, row = A[i - 1], dirs[i]
        for j in range(1, m + 1):
            d = prev[j - 1] + (ai != B[j - 1])
            u = prev[j] + 1
            l = cur[j - 1] + 1
            if d <= u and d <= l:
                cur[j] = d
            elif u <= l:
                cur[j] = u
                row[j] = 1
            else:
                cur[j] = l
                row[j] = 2
        prev = cur
    mapping = [-1] * n
    i, j = n, m
    while i > 0 or j > 0:
        d = dirs[i][j]
        if i > 0 and j > 0 and d == 0:
            mapping[i - 1] = j - 1
            i, j = i - 1, j - 1
        elif i > 0 and (j == 0 or d == 1):
            i -= 1
        else:
            j -= 1

    for t in st:
        t["start"], t["end"] = float("inf"), float("-inf")
    for i in range(n):
        if mapping[i] >= 0:
            t, a = st[a_tok[i]], asr[b_tok[mapping[i]]]
            t["start"], t["end"] = min(t["start"], a["start"]), max(t["end"], a["end"])
    # words the ASR missed sit between their neighbours
    for i, t in enumerate(st):
        if t["start"] != float("inf"):
            continue
        p = next((k for k in range(i - 1, -1, -1) if st[k]["start"] != float("inf")), None)
        q = next((k for k in range(i + 1, len(st)) if st[k]["start"] != float("inf")), None)
        a = st[p]["end"] if p is not None else (st[q]["start"] if q is not None else 0.0)
        b = st[q]["start"] if q is not None else a + LINGER
        t["start"], t["end"] = a, max(a, b)
    for i in range(1, len(st)):
        if st[i]["start"] < st[i - 1]["start"]:
            st[i]["start"] = st[i - 1]["start"]
    return [{"word": t["word"], "start": round(t["start"], 3), "end": round(max(t["start"], t["end"]), 3),
             "line": t["line"]} for t in st]


def _text(ws: list[dict]) -> str:
    return " ".join(w["word"] for w in ws)


def chunk(words: list[dict], max_words: int = 4, max_chars: int = 22, pause: float = 0.25) -> list[dict]:
    """Caption chunks {text, start, end, words} from timed words (ugc-captions rules, language-neutral)."""
    ws = [dict(w) for w in words if str(w.get("word", "")).strip()]
    if not ws:
        return []
    for i, w in enumerate(ws):
        nx = ws[i + 1] if i + 1 < len(ws) else None
        w["_hard"] = bool(HARD.search(w["word"])) or nx is None or ("line" in w and nx.get("line") != w["line"])
        w["_soft"] = bool(SOFT.search(w["word"]))
        w["_gap"] = nx["start"] - w["end"] if nx else 99.0
        w["_glue"] = nx is not None and (bool(NUM.match(w["word"])) or nx["word"][:1] in "%‰")

    def length(a, b):
        return sum(len(w["word"]) for w in ws[a:b]) + (b - a - 1)

    # phrases first: cut at punctuation and pauses; a one-word phrase joins the next (or, at a sentence end, the previous)
    segs, s0 = [], 0
    for i, w in enumerate(ws):
        if not (w["_hard"] or w["_soft"] or w["_gap"] > pause) or w["_glue"]:
            continue
        if i + 1 - s0 == 1 and not w["_hard"] and w["_gap"] <= 1.2 and i + 1 < len(ws):
            continue
        if i + 1 - s0 == 1 and segs and not ws[segs[-1][1] - 1]["_hard"]:
            segs[-1][1] = i + 1
        else:
            segs.append([s0, i + 1])
        s0 = i + 1
    if s0 < len(ws):
        segs.append([s0, len(ws)])

    chunks = []
    for a0, a1 in segs:
        n = a1 - a0
        best, frm = [float("inf")] * (n + 1), [-1] * (n + 1)
        best[0] = 0.0
        for e in range(1, n + 1):
            for b in range(max(0, e - max_words), e):
                if best[b] == float("inf"):
                    continue
                k, c, last = e - b, length(a0 + b, a0 + e), ws[a0 + e - 1]
                if k < 2 and n > 1:
                    continue                                   # no one-word orphans
                if c > 2 * max_chars and k > 1:
                    continue                                   # two lines at most
                if e < n and last["_glue"]:
                    continue
                cost = 10 + (k - 4) * (k - 4) * 0.6
                span = (ws[a0 + e]["start"] if e < n else last["end"]) - ws[a0 + b]["start"]
                if span < 0.7:
                    cost += 10 * (0.7 - span) / 0.7 + 4        # too quick to read
                if e < n:
                    cost += 0 if (last["_soft"] or last["_gap"] > pause) else 5
                for q in range(a0 + b, a0 + e - 1):
                    cost += 7 if ws[q]["_soft"] else (5 if ws[q]["_gap"] > pause else 0)
                if best[b] + cost < best[e]:
                    best[e], frm[e] = best[b] + cost, b
        if best[n] == float("inf"):   # very long words: greedy fill, never cutting after a glued word
            cur, first = [], len(chunks)
            for q in range(a0, a1):
                if cur and not ws[q - 1]["_glue"] and (len(cur) >= max_words or length(q - len(cur), q + 1) > 2 * max_chars):
                    chunks.append(cur)
                    cur = []
                cur.append(ws[q])
            if len(cur) == 1 and len(chunks) > first:      # no one-word tail
                chunks[-1].append(cur[0])
            elif cur:
                chunks.append(cur)
            continue
        cuts, e = [], n
        while e > 0:
            cuts.insert(0, (frm[e], e))
            e = frm[e]
        chunks += [ws[a0 + b:a0 + e] for b, e in cuts]

    # a chunk on screen for under half a second joins a neighbour in the same sentence (if both still fit)
    def fits(a):
        return len(a) <= max_words + 1 and sum(len(w["word"]) for w in a) + len(a) - 1 <= 2 * max_chars

    i = 0
    while i < len(chunks):
        c = chunks[i]
        nx = chunks[i + 1] if i + 1 < len(chunks) else None
        pv = chunks[i - 1] if i > 0 else None
        if (nx[0]["start"] if nx else c[-1]["end"]) - c[0]["start"] >= MIN_SHOWN:
            i += 1
            continue
        can_p = pv is not None and not pv[-1]["_hard"] and fits(pv + c)
        can_n = nx is not None and not c[-1]["_hard"] and fits(c + nx)
        if can_p and (not can_n or len(pv) <= len(nx)):
            chunks[i - 1:i + 1] = [pv + c]
            i -= 1
        elif can_n:
            chunks[i:i + 2] = [c + nx]
        else:
            i += 1

    out = []
    for ci, c in enumerate(chunks):
        start, last_end = c[0]["start"], c[-1]["end"]
        n_in = chunks[ci + 1][0]["start"] if ci + 1 < len(chunks) else None
        if n_in is not None and n_in - last_end <= LONG_PAUSE:
            end = n_in
        else:
            end = last_end + LINGER if n_in is None else min(n_in, last_end + LINGER)
        out.append({"text": _text(c), "start": round(start, 3), "end": round(max(end, last_end), 3),
                    "words": [{k: v for k, v in w.items() if not k.startswith("_")} for w in c]})
    return out


def to_timeline(words: list[dict], dump: dict, vo_in: float = 0.0) -> tuple[list[dict], list[dict]]:
    """VO-file times -> timeline times through the dump's VO segments. A word is kept only if its whole
    span lies inside one VO segment. Without VO segments (plan-based use), the VO starts the timeline
    vo_in seconds into the file."""
    eps = 1e-6
    vo = [s for s in (dump or {}).get("segments", [])
          if s.get("track_type") == "audio" and str(s.get("track") or "").startswith("vo")]
    kept, dropped = [], []
    for w in words:
        hit = None
        if vo:
            for s in vo:
                src_in, speed = s.get("src_in") or 0.0, s.get("speed") or 1.0
                f0, f1 = src_in, src_in + s["duration"] * speed
                if w["start"] >= f0 - eps and w["end"] <= f1 + eps:
                    hit = (s["at"] + (w["start"] - src_in) / speed, s["at"] + (w["end"] - src_in) / speed)
                    break
        elif w["start"] >= vo_in - eps:
            hit = (w["start"] - vo_in, w["end"] - vo_in)
        if hit:
            kept.append({**w, "start": round(max(0.0, hit[0]), 3), "end": round(max(0.0, hit[1]), 3)})
        else:
            dropped.append(dict(w))
    kept.sort(key=lambda w: w["start"])
    return kept, dropped


def temp_en_rows(lines: list[dict], english: list[str]) -> list[dict]:
    """One temporary English text row per script line, timed like the line."""
    if len(lines) != len(english):
        raise ValueError(f"{len(lines)} script lines but {len(english)} English lines")
    return [{"text": en, "at": round(l["start"], 3), "duration": round(max(0.0, l["end"] - l["start"]), 3), "style": "temp_en"}
            for l, en in zip(lines, english)]


def _lines(path: str) -> list[str]:
    return [l.strip() for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def _opt(argv: list[str], name: str, default=None):
    if name in argv:
        i = argv.index(name)
        val = argv[i + 1]
        del argv[i:i + 2]
        return val
    return default


def main(argv: list[str]) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")   # Windows consoles default to cp1252
    argv = list(argv)
    out_path = _opt(argv, "--out")
    max_words = int(_opt(argv, "--max-words", 4))
    if not argv or not out_path:
        raise SystemExit(__doc__)
    cmd, args = argv[0], argv[1:]
    vo = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    if cmd == "chunks" and len(args) == 4:
        words = script_words(vo.get("words", []), _lines(args[1]))
        dump = capcut_project.segments(Path(args[2]), args[3])
        kept, dropped = to_timeline(words, dump)
        chunks = chunk(kept, max_words=max_words)
        Path(out_path).write_text(json.dumps({"chunks": chunks, "dropped_words": dropped}, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
        out = {"chunks": len(chunks), "dropped_words": dropped, "out": out_path}
    elif cmd == "temp-en" and len(args) == 2:
        rows = temp_en_rows(vo.get("lines") or [], _lines(args[1]))
        Path(out_path).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        out = {"rows": len(rows), "out": out_path}
    else:
        raise SystemExit(__doc__)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
