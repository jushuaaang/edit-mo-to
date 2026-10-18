"""QC a batch of generated (Google Flow) clips so the conversation only opens images for flagged ones.

CLI:
    expect <vtype.json> [--out expected.json]
        Build the expected-clips list from a prompt file ({"V1": {"head", "attach", "dur", "text"}, ...}).
    run <clips_dir> <expected.json> [--batch NAME] [--all] [--apply] [--ok FILE,...] [--no-ocr] [--json]
        New files (not already named V##_*) are probed, checksummed, sheeted, OCR'd and matched to expected
        names. Prints one line per clip: PASS/FLAG with reasons. Images go to {tmp}/qc/<batch>/:
        <stem>_sheet.jpg (6 frames over the whole clip) and <stem>_use.jpg (in/mid/out of the use span).
        --all     also QC files already named V##_* (never renamed or moved)
        --apply   rename clean matches to <name>_<title-slug>.mp4 and move flagged files to _rejected/
                  (never deletes). --ok accepts flagged files you checked (false positives).

expected.json:
    {"width": 1080, "height": 1920, "fps": 24, "length_tolerance": 0.1,
     "allowed_text": ["Fascora", "Fascia-First Formula"],   words allowed anywhere (the product's label)
     "brand_words": ["Fascora"],                            product shots must show one of these
     "clips": [{"name": "V01_L06", "length": 4, "keywords": ["hairstylist", "chair"], "product": false,
                "phone": false, "use": "0:00-2:22", "allowed_text": []}]}
    "use" is seconds:frames at 30 fps ("0:00-2:22") or [start, end] in seconds; default the whole clip.
"""
import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from machine import TMP  # noqa: E402

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm"}
NAMED = re.compile(r"^V\d+[a-z]?_", re.I)
SHEET_FRAMES = 6
THUMB_W = 300
OCR_W = 720
OCR_MIN_CONF = 0.6
NEAR_MATCH = 0.75
MATCH_MIN = 0.34
MATCH_MARGIN = 0.1
STOP = set("""a an the and or of in on at to for with by from into onto over under her his their its she he they
it is are was be being as up down out off this that these those one two very about not no while than then
just only also each both all some any slightly behind beside near front back side close wide shot camera
frame image attached matching subject setting action look steady handheld""".split())
PHONE_WORDS = {"lte", "5g", "4g", "imessage", "wifi", "airdrop", "facetime", "safari", "notification"}
CLOCK = re.compile(r"^\d{1,2}[:.]\d{2}$")
COPY_NO = re.compile(r"\s*\(\d+\)$")
BATTERY = re.compile(r"^\d{1,3}\s?%$")


# ---------- small helpers ----------

def parse_sf(s: str, fps: int = 30) -> float:
    """'2:22' -> 2 + 22/30 s; '1:02:05' -> 62 + 5/30 s; plain '2.5' -> 2.5."""
    s = str(s).strip()
    if ":" not in s:
        return float(s)
    parts = [int(p) for p in s.split(":")]
    ff = parts.pop()
    secs = parts.pop()
    mins = parts.pop() if parts else 0
    return mins * 60 + secs + ff / fps


def parse_use(use, duration: float) -> tuple[float, float]:
    if not use:
        return 0.0, duration
    if isinstance(use, (list, tuple)):
        a, b = float(use[0]), float(use[1])
    else:
        a_s, b_s = str(use).split("-", 1)
        a, b = parse_sf(a_s), parse_sf(b_s)
    return max(0.0, a), min(duration, b)


def _stem(word: str) -> str:
    for suf in ("ing", "es", "s"):
        if len(word) > len(suf) + 2 and word.endswith(suf):
            return word[: -len(suf)]
    return word


def tokens(text: str) -> list[str]:
    return [_stem(t) for t in re.findall(r"[a-z]+", text.lower()) if len(t) > 2 and t not in STOP]


def title_words(stem: str) -> list[str]:
    """Flow auto title 'Woman_scooping_powder_in_kitchen_202610151230 (1)' -> the descriptive words."""
    words = re.split(r"[_\s\-]+", stem)
    out = []
    for w in words:
        if re.match(r"^\(?\d{4,}", w):  # Flow's date/time suffix, or a ' (1)' copy number
            break
        out.append(w)
    return out


def slug(words: list[str], n: int = 6) -> str:
    ws = [w.lower() for w in words if re.match(r"^[A-Za-z0-9]+$", w)][:n]
    return "-".join(ws)[:60].strip("-") or "clip"


REASONS = {"duplicate": "duplicate-download", "text": "stray-text", "garbled": "garbled-text", "phone": "phone-ui",
           "length": "wrong-length", "size": "wrong-size", "fps": "wrong-fps", "product": "no-brand-label"}


def reason_slug(flag: str) -> str:
    return REASONS.get(flag.split(" ", 1)[0].lower(), "flagged")


def md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,r_frame_rate:format=duration,size", "-of", "json", str(path)],
        capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    st = (d.get("streams") or [{}])[0]
    num, _, den = st.get("r_frame_rate", "0/1").partition("/")
    return {"width": int(st.get("width", 0)), "height": int(st.get("height", 0)),
            "fps": round(float(num) / float(den or 1), 3) if float(den or 1) else 0.0,
            "duration": round(float(d.get("format", {}).get("duration", 0)), 3),
            "bytes": int(d.get("format", {}).get("size", 0))}


# ---------- checks ----------

def check_specs(info: dict, exp: dict, defaults: dict) -> list[str]:
    flags = []
    tol = float(defaults.get("length_tolerance", 0.1))
    length = exp.get("length", defaults.get("length"))
    if length is not None and abs(info["duration"] - float(length)) > tol:
        flags.append(f"length {info['duration']}s, expected {length}s")
    w, h = defaults.get("width"), defaults.get("height")
    if w and h and (info["width"], info["height"]) != (int(w), int(h)):
        flags.append(f"size {info['width']}x{info['height']}, expected {w}x{h}")
    elif not (w and h) and info["height"] and abs(info["width"] / info["height"] - 9 / 16) > 0.01:
        flags.append(f"size {info['width']}x{info['height']} is not 9:16")
    fps = defaults.get("fps")
    if fps and abs(info["fps"] - float(fps)) > 0.01:
        flags.append(f"fps {info['fps']}, expected {fps}")
    return flags


def classify_text(lines: list[tuple[str, float]], allowed: list[str], phone_ok: bool = False) -> list[dict]:
    """OCR lines -> findings {kind: text|garbled|phone, text, near?}. Junk (1 char, low confidence) is dropped.

    Allowed words pass; a word close to an allowed word is a garbled label; any other word is stray text.
    """
    allow = {w for a in allowed for w in re.findall(r"[a-z0-9]+", a.lower())}
    out = []
    for text, conf in lines:
        t = text.strip()
        if conf < OCR_MIN_CONF or len(re.sub(r"[^A-Za-z0-9]", "", t)) < 2:
            continue
        if CLOCK.match(t) or BATTERY.match(t) or set(re.findall(r"[a-z0-9]+", t.lower())) & PHONE_WORDS:
            if not phone_ok:
                out.append({"kind": "phone", "text": t})
            continue
        kind, near = None, None
        for w in re.findall(r"[a-z0-9]+", t.lower()):
            if len(w) < 2 or w in allow:
                continue
            best = max(allow, key=lambda a: SequenceMatcher(None, w, a).ratio(), default=None)
            if best and SequenceMatcher(None, w, best).ratio() >= NEAR_MATCH:
                kind, near = "garbled", best
                break
            kind = "text"
        if kind:
            item = {"kind": kind, "text": t}
            if near:
                item["near"] = near
            out.append(item)
    return out


def brand_seen(lines: list[tuple[str, float]], brand_words: list[str]) -> bool:
    words = {w for t, c in lines if c >= OCR_MIN_CONF for w in re.findall(r"[a-z0-9]+", t.lower())}
    return any(SequenceMatcher(None, b.lower(), w).ratio() >= NEAR_MATCH for b in brand_words for w in words)


# ---------- frames, sheets, OCR ----------

def frame_times(duration: float, use: tuple[float, float], fps: float) -> tuple[list[float], list[float]]:
    sheet = [round(duration * (i + 0.5) / SHEET_FRAMES, 3) for i in range(SHEET_FRAMES)]
    a, b = use
    last = max(a, b - 1 / (fps or 30))
    return sheet, [round(a, 3), round((a + b) / 2, 3), round(last, 3)]


def grab(video: Path, t: float, out: Path) -> Path:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
                    "-vf", f"scale={OCR_W}:-2", "-q:v", "3", str(out)], check=True)
    return out


def strip(frames: list[tuple[float, Path]], out: Path, thumb_w: int = THUMB_W) -> Path:
    from PIL import Image, ImageDraw
    thumbs = []
    for t, p in frames:
        im = Image.open(p).convert("RGB")
        im = im.resize((thumb_w, round(im.height * thumb_w / im.width)))
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, 52, 16], fill=(0, 0, 0))
        d.text((3, 2), f"{t:.2f}s", fill=(255, 255, 0))
        thumbs.append(im)
    sheet = Image.new("RGB", (thumb_w * len(thumbs) + 2 * (len(thumbs) - 1), max(i.height for i in thumbs)), "white")
    for i, im in enumerate(thumbs):
        sheet.paste(im, (i * (thumb_w + 2), 0))
    sheet.save(out, quality=80)
    return out


_OCR = None


def ocr_engine():
    global _OCR
    if _OCR is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _OCR = RapidOCR()
        except Exception:  # not installed: QC still runs, without the text checks
            _OCR = False
    return _OCR


def ocr(path: Path) -> list[tuple[str, float]]:
    eng = ocr_engine()
    if not eng:
        return []
    res, _ = eng(str(path))
    return [(r[1], float(r[2])) for r in (res or [])]


# ---------- matching and naming ----------

def match_score(title: list[str], exp: dict) -> float:
    tt = set(tokens(" ".join(title)))
    if not tt:
        return 0.0
    et = set(tokens(" ".join(exp.get("keywords", [])) + " " + exp.get("name", "").replace("_", " ")))
    return round(len(tt & et) / len(tt), 3)


def propose(title: list[str], expected: list[dict]) -> dict:
    scores = sorted(((match_score(title, e), e["name"]) for e in expected), reverse=True)
    if not scores or scores[0][0] < MATCH_MIN:
        return {"name": None, "score": scores[0][0] if scores else 0.0, "why": "no match"}
    second = scores[1][0] if len(scores) > 1 else 0.0
    if scores[0][0] - second < MATCH_MARGIN:
        tied = [n for s, n in scores if scores[0][0] - s < MATCH_MARGIN]
        return {"name": None, "score": scores[0][0], "why": "ambiguous: " + "/".join(tied[:4])}
    return {"name": scores[0][1], "score": scores[0][0]}


def with_take(name: str, letter: str) -> str:
    """'V21_L22' + 'b' -> 'V21b_L22' (the folder's convention for alternate takes)."""
    m = re.match(r"^(V\d+)(.*)$", name)
    return f"{m.group(1)}{letter}{m.group(2)}" if m else f"{name}{letter}"


def target_name(name: str, title: list[str], ext: str, taken: set[str]) -> str:
    prefixes = {re.match(r"^(V\d+[a-z]?)_", t, re.I).group(1).lower() for t in taken if NAMED.match(t)}
    base = name
    for letter in ["", *"bcdefgh"]:
        cand = with_take(name, letter) if letter else name
        if cand.split("_")[0].lower() not in prefixes:
            base = cand
            break
    return f"{base}_{slug(title)}{ext}"


def reject_name(stem: str, name: str | None, reason: str, ext: str, rejected_dir: Path) -> str:
    if not name:
        return f"{stem}{ext}"
    existing = list(rejected_dir.glob(f"{name}_try*")) if rejected_dir.exists() else []
    return f"{name}_try{len(existing) + 1}_{reason}{ext}"


# ---------- main run ----------

def qc_clip(video: Path, exp: dict | None, cfg: dict, outdir: Path, use_ocr: bool) -> dict:
    exp = exp or {}
    info = probe(video)
    flags = check_specs(info, exp, cfg)
    use = parse_use(exp.get("use"), info["duration"])
    sheet_t, use_t = frame_times(info["duration"], use, info["fps"])
    fdir = outdir / "frames"
    fdir.mkdir(parents=True, exist_ok=True)
    sheet_f = [(t, grab(video, t, fdir / f"{video.stem}_{t:.2f}.jpg")) for t in sheet_t]
    use_f = [(t, grab(video, t, fdir / f"{video.stem}_{t:.2f}.jpg")) for t in use_t]
    strip(sheet_f, outdir / f"{video.stem}_sheet.jpg")
    strip(use_f, outdir / f"{video.stem}_use.jpg")
    findings, all_lines = {}, []
    if use_ocr:
        allowed = list(cfg.get("allowed_text", [])) + list(exp.get("allowed_text", []))
        for t, p in sorted(set(sheet_f + use_f)):
            lines = ocr(p)
            all_lines += lines
            for f in classify_text(lines, allowed, phone_ok=bool(exp.get("phone"))):
                findings.setdefault((f["kind"], f["text"].upper()), {**f, "times": []})["times"].append(t)
        for f in findings.values():
            near = f" (near '{f['near']}')" if f.get("near") else ""
            when = ",".join(f"{t:.2f}s" for t in f["times"][:4])
            flags.append(f"{f['kind']} '{f['text']}'{near} @{when}")
        if exp.get("product") and cfg.get("brand_words") and not brand_seen(all_lines, cfg["brand_words"]):
            flags.append("product shot: brand label not read")
    return {"file": video.name, **info, "flags": flags}


def run(clips_dir: Path, expected_path: Path, batch: str | None = None, include_named: bool = False,
        apply: bool = False, ok: set[str] = frozenset(), use_ocr: bool = True) -> dict:
    cfg = json.loads(expected_path.read_text(encoding="utf-8"))
    expected = cfg.get("clips", [])
    by_prefix = {e["name"].split("_")[0].lower(): e for e in expected}
    batch = batch or f"{clips_dir.parent.name}_{time.strftime('%Y%m%d-%H%M%S')}"
    outdir = TMP / "qc" / batch
    outdir.mkdir(parents=True, exist_ok=True)
    rejected_dir = clips_dir / "_rejected"

    # browser re-downloads ("name (1).mp4") sort after the original, so the copy is the one flagged
    files = sorted((p for p in clips_dir.iterdir() if p.suffix.lower() in VIDEO_EXT and p.is_file()),
                   key=lambda p: (COPY_NO.sub("", p.stem), bool(COPY_NO.search(p.stem)), p.name))
    new = [p for p in files if not NAMED.match(p.name)]
    todo = files if include_named else new
    known = {}  # checksum -> file, for kept and rejected clips
    for p in [*files, *(sorted(rejected_dir.iterdir()) if rejected_dir.exists() else [])]:
        if p.is_file() and p.suffix.lower() in VIDEO_EXT and (NAMED.match(p.name) or p.parent == rejected_dir):
            known.setdefault(md5(p), p)

    ocr_ok = use_ocr and bool(ocr_engine())
    results, seen = [], {}
    for p in todo:
        named = bool(NAMED.match(p.name))
        if named:
            prefix = re.match(r"^(V\d+)", p.name, re.I).group(1).lower()
            exp = by_prefix.get(prefix) or by_prefix.get("v" + str(int(prefix[1:])))
            m = {"name": exp["name"] if exp else None, "score": None, "why": "already named"}
        else:
            m = propose(title_words(p.stem), expected)
            exp = next((e for e in expected if e["name"] == m["name"]), None)
        r = qc_clip(p, exp, cfg, outdir, ocr_ok)
        r["match"] = m
        h = md5(p)
        dup = seen.get(h) or (known.get(h) if known.get(h) != p else None)
        if dup:
            r["flags"].insert(0, f"duplicate of {dup.name}")
        seen.setdefault(h, p)
        r["named"] = named
        r["status"] = "PASS" if not r["flags"] or p.name in ok else "FLAG"
        results.append(r)

    if apply:
        taken = {p.name for p in files}
        for r in results:
            if r["named"]:
                continue
            src = clips_dir / r["file"]
            title = title_words(src.stem)
            if r["status"] == "FLAG":
                rejected_dir.mkdir(exist_ok=True)
                reason = reason_slug(r["flags"][0])
                dst = rejected_dir / reject_name(src.stem, r["match"]["name"], reason, src.suffix, rejected_dir)
            elif r["match"]["name"]:
                dst = clips_dir / target_name(r["match"]["name"], title, src.suffix, taken)
            else:
                continue
            if dst.exists():
                r["action"] = f"skipped: {dst.name} exists"
                continue
            src.rename(dst)
            taken.add(dst.name)
            r["action"] = f"-> {dst.relative_to(clips_dir).as_posix()}"

    report = {"batch": batch, "images": outdir.as_posix(), "ocr": ocr_ok, "new": len(new),
              "checked": len(results), "flagged": sum(r["status"] == "FLAG" for r in results),
              "clips": results}
    (outdir / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def table(report: dict) -> str:
    rows = [f"batch {report['batch']}: {report['checked']} checked ({report['new']} new), "
            f"{report['flagged']} flagged, OCR {'on' if report['ocr'] else 'OFF'}; images {report['images']}/",
            "file | match | status | reasons"]
    for r in report["clips"]:
        m = r["match"]
        match = m["name"] or m.get("why", "-")
        if m.get("score") is not None and m["name"]:
            match += f" ({m['score']})"
        line = f"{r['file']} | {match} | {r['status']} | {'; '.join(r['flags']) or '-'}"
        if r.get("action"):
            line += f" | {r['action']}"
        rows.append(line)
    return "\n".join(rows)


# ---------- expected list from a prompt file ----------

def expected_from_vtype(vtype: dict) -> dict:
    clips = []
    for key, v in vtype.items():
        head, text = v.get("head", ""), v.get("text", "")
        num = int(re.match(r"V(\d+)", key).group(1))
        line = re.search(r"Line\s+(\w+)", head)
        name = f"V{num:02d}" + (f"_L{int(line.group(1)):02d}" if line and line.group(1).isdigit()
                                 else f"_{line.group(1)}" if line else "")
        use = re.search(r"use the first ([\d:]+)", head)
        subject = re.search(r"SUBJECT:(.*?)(?:\b[A-Z]{4,}:|$)", text, re.S)
        action = re.search(r"ACTION:(.*?)(?:\b[A-Z]{4,}:|$)", text, re.S)
        words = tokens((subject.group(1) if subject else "") + " " + (action.group(1) if action else ""))
        kw = list(dict.fromkeys(w for w in words if not w.isdigit()))[:25]
        clips.append({"name": name, "length": float(v.get("dur") or 0) or None, "keywords": kw,
                      "product": "Product" in v.get("attach", []),
                      "phone": "phone" in " ".join(m.group(1) for m in (subject, action) if m).lower(),
                      "use": f"0:00-{use.group(1)}" if use else None})
    return {"width": 1080, "height": 1920, "fps": 24, "length_tolerance": 0.1,
            "allowed_text": [], "brand_words": [], "clips": clips}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("expect")
    e.add_argument("vtype")
    e.add_argument("--out")
    r = sub.add_parser("run")
    r.add_argument("clips_dir")
    r.add_argument("expected")
    r.add_argument("--batch")
    r.add_argument("--all", action="store_true")
    r.add_argument("--apply", action="store_true")
    r.add_argument("--ok", default="")
    r.add_argument("--no-ocr", action="store_true")
    r.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "expect":
        out = json.dumps(expected_from_vtype(json.loads(Path(a.vtype).read_text(encoding="utf-8"))), indent=1)
        Path(a.out).write_text(out, encoding="utf-8") if a.out else print(out)
        return
    rep = run(Path(a.clips_dir), Path(a.expected), a.batch, a.all, a.apply,
              {s.strip() for s in a.ok.split(",") if s.strip()}, not a.no_ocr)
    print(json.dumps(rep, indent=1) if a.json else table(rep))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
