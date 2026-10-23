"""Render edit-mo-to motion overlays (HyperFrames templates) to transparent 9:16 ProRes 4444 .mov files.

Templates live in ..\\motion\\templates\\<name>.html. Each starts with
    <!--defaults {"text": "...", "duration": 4, ...} -->
and uses {{key}} placeholders. Values are HTML-escaped. Verified 2026-10-16: CapCut 9.6 keeps the
alpha of these .mov files on an overlay track.

CLI (prints JSON):
    list                                         templates and their variables/defaults
    render <template> <out.mov> [--vars '<json>' | --vars-file f.json] [--no-slim] [--workers N]
                                                 one worker by default (machine.json render_workers; 0 = HyperFrames'
                                                 own choice), then a slim ProRes 4444 re-encode (about 40% smaller)
    render-many <jobs.json> [--concurrency N]    [{"template","out","vars"}...]; identical jobs render once and are
                                                 copied; the rest run side by side (machine.json render_concurrency)
    check <template> [--vars '<json>' | --vars-file f.json] [--snapshots dir]
                                                 HyperFrames audit: lint, runtime errors, text overflow/overlap,
                                                 contrast. Held problems are errors/warnings; entrance blips are info
    preview <file.mov> <out.png> [seconds]       one frame composited over green (check transparency)
    trace <logo.png> <out.svg> [--threshold 0-255] [--invert]
                                                 trace a PNG logo to a one-colour SVG outline (OpenCV
                                                 contours, holes kept), for logo-reveal when no SVG exists
    cutout <clip> <out.mov> [--in s] [--len s]   the person alone on alpha (HyperFrames u2net_human_seg,
                                                 ~1.3 s/frame on CPU), for text/graphics BEHIND the speaker:
                                                 place it on a track above those overlays, same at/scale/xy
                                                 as the A-roll segment it was cut from

Vars whose value is an existing media file (video/image path) are copied into the render, so templates
can show the user's own clips (phone-cards). Vars that point at an existing .svg file are replaced by the
file's markup (scripts and event handlers removed), so logo-reveal can draw the real logo's paths. Vars that
point at an existing .json or .txt file are replaced by its text (ugc-captions reads word timings + the script).
"""
import concurrent.futures
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MOTION = Path(__file__).resolve().parents[1] / "motion"
TEMPLATES = MOTION / "templates"
HF_BIN = MOTION / "node_modules" / ".bin" / ("hyperframes.cmd" if os.name == "nt" else "hyperframes")
DEFAULTS_RE = re.compile(r"\A\s*<!--defaults\s+(\{.*?\})\s*-->\s*", re.S)
PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")
GSAP_CDN = "https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"  # copied into skeleton/, so renders work offline


HELD_DEFECTS = {"canvas_overflow", "text_box_overflow", "clipped_text", "content_overlap", "text_occluded"}
# Lint rules about HyperFrames Studio's own timeline UI, not the rendered pixels: our overlays are single
# self-contained renders, never edited in Studio, so these are informational for us.
STUDIO_ONLY = {"nested_structure_needs_subcomposition"}


class RenderFailed(RuntimeError):
    pass


def _split(template: str) -> tuple[dict, str]:
    m = DEFAULTS_RE.match(template)
    if not m:
        raise ValueError("template must start with <!--defaults {...} -->")
    return json.loads(m.group(1)), template[m.end():]


def fill(template: str, variables: dict) -> str:
    defaults, body = _split(template)
    unknown = set(variables) - set(defaults)
    if unknown:
        raise ValueError(f"unknown variable(s) {sorted(unknown)}; template has {sorted(defaults)}")
    values = {**defaults, **variables}
    try:
        values["duration"] = float(values["duration"])
        if values["duration"] <= 0:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise ValueError(f"duration must be a positive number, got {values.get('duration')!r}")

    def sub(m):
        key = m.group(1)
        if key not in values:
            raise ValueError(f"placeholder {{{{{key}}}}} has no default")
        v = values[key]
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        return html.escape(str(v), quote=True)

    return PLACEHOLDER_RE.sub(sub, body).replace(GSAP_CDN, "gsap.min.js")


def template_text(name: str) -> str:
    path = TEMPLATES / f"{name}.html"
    if not path.exists():
        raise FileNotFoundError(f"no template {name!r}; have {sorted(list_templates())}")
    return path.read_text(encoding="utf-8")


def list_templates() -> dict:
    out = {}
    for p in sorted(TEMPLATES.glob("*.html")):
        defaults, _ = _split(p.read_text(encoding="utf-8"))
        out[p.stem] = {"defaults": defaults}
    return out


def _probe(path: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "stream=pix_fmt,width,height:format=duration", "-of", "json", str(path)],
                       capture_output=True, text=True)
    d = json.loads(r.stdout or "{}")
    s = (d.get("streams") or [{}])[0]
    return {"width": s.get("width"), "height": s.get("height"), "pix_fmt": s.get("pix_fmt"),
            "alpha": (s.get("pix_fmt") or "").startswith(("yuva", "rgba", "argb", "bgra", "abgr", "gbrap", "ya")),
            "duration": float((d.get("format") or {}).get("duration") or 0)}


TEXT_EXT = {".json", ".txt"}  # vars pointing at these become the file's text (HTML-escaped like any value)
MEDIA_EXT = {".mp4", ".mov", ".webm", ".m4v", ".png", ".jpg", ".jpeg", ".webp"}


def svg_markup(path: Path) -> str:
    """An SVG file's <svg>…</svg> markup, without the XML prolog, comments, scripts or on* handlers."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"<\?xml.*?\?>|<!DOCTYPE.*?>|<!--.*?-->", "", text, flags=re.S | re.I)
    text = re.sub(r"<script\b.*?</script>|<foreignObject\b.*?</foreignObject>", "", text, flags=re.S | re.I)
    text = re.sub(r"\son[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*')", "", text, flags=re.I)
    m = re.search(r"<svg\b.*</svg>", text, flags=re.S | re.I)
    if not m:
        raise ValueError(f"{path} has no <svg> element")
    return re.sub(r"\s+", " ", m.group(0)).strip()


def trace(png: Path, out: Path, threshold: int | None = None, invert: bool = False) -> dict:
    """Trace a logo PNG to a one-colour SVG: the alpha channel if it has one, else dark-on-light (or light-on-
    dark with invert) by Otsu or the given threshold. Outer shapes and their holes become one even-odd path."""
    import cv2

    img = cv2.imread(str(png), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"cannot read {png}")
    if img.ndim == 3 and img.shape[2] == 4 and img[:, :, 3].min() < 250:
        gray, dark_is_ink = img[:, :, 3], False
    else:
        gray = cv2.cvtColor(img[:, :, :3], cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
        dark_is_ink = not invert
    # trace at >= 1600 px wide so curves stay smooth after polygon simplification
    k = max(1.0, 1600 / gray.shape[1])
    gray = cv2.resize(gray, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
    flag = cv2.THRESH_BINARY_INV if dark_is_ink else cv2.THRESH_BINARY
    if threshold is None:
        _, mask = cv2.threshold(gray, 0, 255, flag | cv2.THRESH_OTSU)
    else:
        _, mask = cv2.threshold(gray, threshold, 255, flag)
    contours, _ = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    h, w = mask.shape
    min_area = w * h * 2e-5
    polys = [cv2.approxPolyDP(c, 0.6, True).reshape(-1, 2) / k for c in contours if abs(cv2.contourArea(c)) >= min_area]
    if not polys:
        raise ValueError("nothing traced; try --threshold or --invert")
    # tight viewBox around the ink, with a 1% margin
    pts = [p for c in polys for p in c]
    x0, y0 = min(p[0] for p in pts), min(p[1] for p in pts)
    pad = 0.01 * max(max(p[0] for p in pts) - x0, max(p[1] for p in pts) - y0)
    x0, y0 = x0 - pad, y0 - pad
    W, H = max(p[0] for p in pts) - x0 + pad, max(p[1] for p in pts) - y0 + pad
    parts = ["M" + " L".join(f"{x - x0:.1f},{y - y0:.1f}" for x, y in c) + "Z" for c in polys]
    Path(out).write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}">'
                         f'<path fill="#000" fill-rule="evenodd" d="{" ".join(parts)}"/></svg>\n', encoding="utf-8")
    return {"svg": str(out), "shapes": len(parts), "viewbox": f"0 0 {W:.0f} {H:.0f}"}


def _stage_media(variables: dict, work: Path) -> dict:
    """Copy vars that point at real media files into the render folder; the template sees a relative name.
    A var pointing at an .svg file becomes that file's markup; at a .json/.txt file, that file's text."""
    out = dict(variables)
    for k, v in variables.items():
        if isinstance(v, str) and v.lower().endswith(".svg") and Path(v).is_file():
            out[k] = svg_markup(Path(v))
            continue
        if isinstance(v, str) and Path(v).suffix.lower() in TEXT_EXT and Path(v).is_file():
            out[k] = Path(v).read_text(encoding="utf-8-sig")
            if Path(v).suffix.lower() == ".json":  # one line, so the composition stays small for HyperFrames' lint
                out[k] = json.dumps(json.loads(out[k]), ensure_ascii=False, separators=(",", ":"))
            continue
        if isinstance(v, str) and Path(v).suffix.lower() in MEDIA_EXT and Path(v).is_file():
            name = f"media_{k}{Path(v).suffix.lower()}"
            shutil.copy2(v, work / name)
            out[k] = name
    return out


def slim(mov: Path) -> dict:
    """Re-encode a render as a lighter ProRes 4444 (about 40% smaller, within 0.3 of one 8-bit step), in place.
    Writes <mov>.slim.tmp.mov beside it, then replaces the original; on failure the original stays."""
    mov = Path(mov)
    tmp = mov.with_name(mov.name + ".slim.tmp.mov")
    before = mov.stat().st_size
    try:
        r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(mov), "-c:v", "prores_ks",
                            "-profile:v", "4444", "-vendor", "apl0", "-pix_fmt", "yuva444p10le", "-qscale:v", "6",
                            "-alpha_bits", "8", "-an", str(tmp)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0 or not tmp.exists():
            raise RenderFailed(f"slim re-encode of {mov} failed ({r.returncode}): {r.stderr[-800:]}")
        os.replace(tmp, mov)
    finally:
        tmp.unlink(missing_ok=True)
    after = mov.stat().st_size
    return {"before": before, "after": after, "ratio": round(after / before, 3) if before else None}


def _config_int(key: str) -> int:
    from machine import load
    return int(load()[key])


def render(name: str, out: Path, variables: dict | None = None, fps: int = 30, workers: int | None = None,
           slim: bool = True) -> dict:
    """Render one overlay. workers None = machine.json render_workers (default 1: skips HyperFrames' ~1.7 s
    worker-calibration browser launch); 0 = don't pass --workers. slim re-encodes the result smaller."""
    slim_fn = globals()["slim"]
    out = Path(out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    workers = _config_int("render_workers") if workers is None else workers
    work = Path(tempfile.mkdtemp(prefix="emt-motion-", dir=os.environ.get("EMT_MOTION_TMP")))
    try:
        html_text = fill(template_text(name), _stage_media(variables or {}, work))
        for f in (MOTION / "skeleton").iterdir():
            shutil.copy2(f, work / f.name)
        (work / "index.html").write_text(html_text, encoding="utf-8")
        env = {**os.environ, "HYPERFRAMES_SKIP_SKILLS": "1"}
        args = [str(HF_BIN), "render", str(work), "--format", "mov", "--fps", str(fps), "-o", str(out), "--quiet"]
        if workers:
            args += ["--workers", str(workers)]
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
                           shell=os.name == "nt")
        if r.returncode != 0 or not out.exists():
            raise RenderFailed(f"hyperframes render failed ({r.returncode}): {(r.stderr or r.stdout)[-1500:]}")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    info = _probe(out)
    if not info["alpha"]:
        raise RenderFailed(f"{out} has no alpha channel ({info['pix_fmt']})")
    if slim:
        slim_fn(out)
    return {"file": str(out), "template": name, **info, "bytes": out.stat().st_size}


def job_key(template: str, variables: dict, duration: float) -> str:
    """Same template + vars + duration (media vars by path) -> same key, so the render can be shared."""
    blob = json.dumps([template, variables, float(duration)], sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


def render_many(jobs: list[dict], concurrency: int | None = None, render_fn=render) -> list[dict]:
    """Render jobs [{"template", "out", "vars"}] side by side (one subprocess each). Jobs with the same
    job_key render once; the rest get a copy and "copied_from" in their result. One result per job, in order."""
    if concurrency is None:
        concurrency = _config_int("render_concurrency")
    firsts: dict[str, int] = {}
    dupes: dict[int, int] = {}
    for i, j in enumerate(jobs):
        v = j.get("vars") or {}
        dur = v["duration"] if "duration" in v else list_templates()[j["template"]]["defaults"].get("duration", 0)
        k = job_key(j["template"], v, float(dur))
        if k in firsts:
            dupes[i] = firsts[k]
        else:
            firsts[k] = i
    results: list[dict | None] = [None] * len(jobs)
    todo = [i for i in range(len(jobs)) if i not in dupes]
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futs = {pool.submit(render_fn, jobs[i]["template"], Path(jobs[i]["out"]), jobs[i].get("vars") or {}): i
                for i in todo}
        for f in concurrent.futures.as_completed(futs):
            results[futs[f]] = f.result()
    for i, src in dupes.items():
        out = Path(jobs[i]["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(jobs[src]["out"], out)
        results[i] = {**results[src], "file": str(out.resolve()), "copied_from": str(Path(jobs[src]["out"]).resolve())}
    return results


def check(name: str, variables: dict | None = None, snapshots_dir: Path | None = None) -> dict:
    """Run HyperFrames' `check` (lint, runtime errors, layout overflow/overlap, WCAG contrast) on a filled
    template. Returns {ok, errors, warnings, info} with each finding's code, selector, time and message.
    Transient issues during entrance/exit animations come back as info; held ones as warnings/errors."""
    defaults, _ = _split(template_text(name))
    dur = float({**defaults, **(variables or {})}["duration"])
    hold = [round(dur * f, 3) for f in (0.35, 0.5, 0.65)]
    work = Path(tempfile.mkdtemp(prefix="emt-check-", dir=os.environ.get("EMT_MOTION_TMP")))
    try:
        html_text = fill(template_text(name), _stage_media(variables or {}, work))
        for f in (MOTION / "skeleton").iterdir():
            shutil.copy2(f, work / f.name)
        (work / "index.html").write_text(html_text, encoding="utf-8")
        args = [str(HF_BIN), "check", str(work), "--json", "--at", ",".join(map(str, hold))]
        if snapshots_dir:
            args.append("--snapshots")
        env = {**os.environ, "HYPERFRAMES_SKIP_SKILLS": "1"}
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, shell=os.name == "nt", timeout=600)
        start = r.stdout.find("{")
        if start < 0:
            raise RenderFailed(f"hyperframes check gave no JSON ({r.returncode}): {(r.stderr or r.stdout)[-1500:]}")
        data = json.loads(r.stdout[start:])
        if snapshots_dir:
            snapshots_dir = Path(snapshots_dir)
            snapshots_dir.mkdir(parents=True, exist_ok=True)
            for png in work.rglob("*.png"):
                shutil.copy2(png, snapshots_dir / png.name)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    out = {"ok": bool(data.get("ok")), "browser_skipped": bool(data.get("browserSkipped")),
           "errors": [], "warnings": [], "info": []}
    for section in ("lint", "runtime", "layout", "motion", "contrast"):
        for f in (data.get(section) or {}).get("findings") or []:
            if not isinstance(f, dict):
                continue
            sev = {"error": "errors", "warning": "warnings"}.get(f.get("severity"), "info")
            if f.get("code") in STUDIO_ONLY:
                sev = "info"
            # HyperFrames grades short overlays' overflow as info; text cut off while the overlay is
            # holding still (not just flying in/out) is a real defect, so promote it.
            t = f.get("time")
            if (sev == "info" and section == "layout" and f.get("code") in HELD_DEFECTS
                    and isinstance(t, (int, float)) and 0.25 * dur <= t <= 0.8 * dur):
                sev = "warnings"
            out[sev].append({"section": section, "code": f.get("code"), "selector": f.get("selector"),
                             "time": f.get("time"), "message": f.get("message"), "text": f.get("text"),
                             "fix": f.get("fixHint") or f.get("suggestedColor")})
    return out


def preview(mov: Path, png: Path, at: float | None = None) -> Path:
    info = _probe(Path(mov))
    t = info["duration"] / 2 if at is None else at
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x00aa44:s=1080x1920",
                    "-ss", str(t), "-i", str(mov), "-filter_complex", "[0][1]overlay,scale=360:-1",
                    "-frames:v", "1", str(png)], check=True)
    return Path(png)


def cutout(clip: Path, out: Path, start: float = 0.0, length: float | None = None) -> dict:
    """Person-only transparent .mov of clip[start:start+length], at the clip's own frame rate."""
    out = Path(out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="emt-cutout-", dir=os.environ.get("EMT_MOTION_TMP")))
    try:
        src = work / "src.mp4"
        # keep the source frame rate, so the cutout's frames line up 1:1 with the A-roll it sits on
        dur = ["-t", f"{length:.4f}"] if length else []
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{start:.4f}", "-i", str(clip), *dur,
                        "-an", "-c:v", "libx264", "-crf", "12", str(src)], check=True)
        env = {**os.environ, "HYPERFRAMES_SKIP_SKILLS": "1", "CI": "1"}
        r = subprocess.run([str(HF_BIN), "remove-background", str(src), "-o", str(out), "--quality", "best"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, shell=os.name == "nt")
        if r.returncode != 0 or not out.exists():
            raise RenderFailed(f"remove-background failed ({r.returncode}): {(r.stderr or r.stdout)[-800:]}")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    info = _probe(out)
    if not info["alpha"]:
        raise RenderFailed(f"{out} has no alpha channel ({info['pix_fmt']})")
    return {"file": str(out), "source": str(clip), "in": start, **info}


def main(argv: list[str]) -> None:
    if not argv or argv[0] in ("-h", "--help"):
        raise SystemExit(__doc__)
    cmd, args = argv[0], argv[1:]
    if cmd == "list":
        out = list_templates()
    elif cmd == "render":
        variables = {}
        if "--vars" in args:
            i = args.index("--vars")
            variables = json.loads(args[i + 1])
            args = args[:i] + args[i + 2:]
        if "--vars-file" in args:
            i = args.index("--vars-file")
            variables = json.loads(Path(args[i + 1]).read_text(encoding="utf-8"))
            args = args[:i] + args[i + 2:]
        workers = None
        if "--workers" in args:
            i = args.index("--workers")
            workers = int(args[i + 1])
            args = args[:i] + args[i + 2:]
        no_slim = "--no-slim" in args
        args = [a for a in args if a != "--no-slim"]
        out = render(args[0], Path(args[1]), variables, workers=workers, slim=not no_slim)
    elif cmd == "render-many":
        conc = int(args[args.index("--concurrency") + 1]) if "--concurrency" in args else None
        out = render_many(json.loads(Path(args[0]).read_text(encoding="utf-8-sig")), conc)
    elif cmd == "check":
        variables = {}
        snaps = None
        if "--vars" in args:
            i = args.index("--vars")
            variables = json.loads(args[i + 1])
            args = args[:i] + args[i + 2:]
        if "--vars-file" in args:
            i = args.index("--vars-file")
            variables = json.loads(Path(args[i + 1]).read_text(encoding="utf-8"))
            args = args[:i] + args[i + 2:]
        if "--snapshots" in args:
            i = args.index("--snapshots")
            snaps = Path(args[i + 1])
            args = args[:i] + args[i + 2:]
        out = check(args[0], variables, snaps)
    elif cmd == "cutout":
        start = float(args[args.index("--in") + 1]) if "--in" in args else 0.0
        length = float(args[args.index("--len") + 1]) if "--len" in args else None
        out = cutout(Path(args[0]), Path(args[1]), start, length)
    elif cmd == "trace":
        thr = int(args[args.index("--threshold") + 1]) if "--threshold" in args else None
        out = trace(Path(args[0]), Path(args[1]), thr, "--invert" in args)
    elif cmd == "preview":
        out = {"png": str(preview(Path(args[0]), Path(args[1]), float(args[2]) if len(args) > 2 else None))}
    else:
        raise SystemExit(__doc__)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1:])
