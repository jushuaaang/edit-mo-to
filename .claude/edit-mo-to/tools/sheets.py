"""Tiled, labelled frame sheets: one image to look at instead of dozens of single frames.
clip_sheets / overlay_sheets for a plan timeline, inventory for a folder of raw clips.
CLI: clips <plan.json> "<timeline>" <out_dir> [--ai] | overlays <plan.json> "<timeline>" <out_dir>
     | inventory <folder> <out_dir> [--max N]"""
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import plan_tools as pt

CELL_W, CELL_H = 270, 480
STRIP_W, ROW_H = 1080, 340   # inventory: one 6-frame strip per row, 6 rows per sheet
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}


def grab(video: str, t: float, out: Path, w: int = CELL_W) -> Path:
    """One frame of `video` at `t` seconds, scaled to width `w`, as a PNG."""
    out = Path(out); out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{max(t, 0):.3f}", "-i", str(video),
                    "-frames:v", "1", "-vf", f"scale={w}:-2", str(out)], check=True)
    return out


def _label(d: ImageDraw.ImageDraw, x: int, y: int, text: str, font) -> None:
    box = d.textbbox((x + 6, y + 6), text, font=font)
    d.rectangle((x, y, box[2] + 4, box[3] + 4), fill=(0, 0, 0))
    d.text((x + 6, y + 6), text, fill=(255, 255, 255), font=font)


def tile(frames: list[tuple[str, Path]], out: Path, cols: int = 4, rows: int = 3) -> Path:
    """Grid of (label, image) cells, each fitted into 270x480 and labelled top-left on a dark box."""
    out = Path(out); out.parent.mkdir(parents=True, exist_ok=True)
    sheet = Image.new("RGB", (cols * CELL_W, rows * CELL_H), (0, 0, 0))
    font = ImageFont.load_default()
    d = ImageDraw.Draw(sheet)
    for i, (label, path) in enumerate(frames[:cols * rows]):
        x, y = (i % cols) * CELL_W, (i // cols) * CELL_H
        im = Image.open(path).convert("RGB")
        im.thumbnail((CELL_W, CELL_H))
        sheet.paste(im, (x + (CELL_W - im.width) // 2, y + (CELL_H - im.height) // 2))
        _label(d, x, y, label, font)
    sheet.save(out)
    return out


def _paged(cells: list[tuple[str, Path]], out_dir: Path, stem: str, per: int = 12) -> list[dict]:
    res = []
    for n in range(0, len(cells), per):
        page = cells[n:n + per]
        p = tile(page, Path(out_dir) / f"{stem}_{n // per + 1}.png")
        res.append({"path": str(p), "items": [lbl for lbl, _ in page]})
    return res


def _timeline(plan: dict, name: str) -> dict:
    return next(t for t in plan["timelines"] if t["name"] == name)


def _speed(c: dict) -> float:
    return c.get("speed") or 1


def clip_sheets(plan: dict, timeline: str, out_dir: Path, ai: bool = False) -> dict:
    """Each clip's middle source frame, 12 per sheet; with `ai`, in/mid/out as three cells per clip."""
    out_dir = Path(out_dir)
    cells = []
    for n, c in enumerate(_timeline(plan, timeline)["clips"], 1):
        a, b = c["src_in"], c["src_out"]
        picks = ([("in", a), ("mid", (a + b) / 2), ("out", max(a, b - 0.05))] if ai
                 else [("", (a + b) / 2)])
        for tag, t in picks:
            lbl = f"{n}·{tag}" if tag else str(n)
            cells.append((lbl, grab(c["file"], t, out_dir / "frames" / f"c{n}_{tag or 'mid'}.png")))
    return {"sheets": _paged(cells, out_dir, f"clips_{timeline}")}


def overlay_sheets(plan: dict, timeline: str, out_dir: Path) -> dict:
    """Each overlay's middle frame composited on the clip under it at that time (label ov<n>).
    An overlay with no rendered file yet is labelled with its template and shown as the clip frame alone."""
    out_dir = Path(out_dir)
    tl = _timeline(plan, timeline)
    cells = []
    for n, o in enumerate(tl.get("overlays", []), 1):
        t = o["at"] + o["duration"] / 2
        under = next((c for c in tl["clips"]
                      if c["at"] <= t < c["at"] + (c["src_out"] - c["src_in"]) / _speed(c)), None)
        f = out_dir / "frames" / f"ov{n}.png"
        lbl = f"ov{n}"
        try:
            if under is None:
                raise LookupError("no clip under overlay")
            base = Image.open(grab(under["file"], under["src_in"] + (t - under["at"]) * _speed(under),
                                   f)).convert("RGBA")
            if o.get("file") and Path(o["file"]).exists():
                ov = grab(o["file"], o["duration"] / 2, out_dir / "frames" / f"ov{n}_o.png")
                base = Image.alpha_composite(base, Image.open(ov).convert("RGBA").resize(base.size))
            else:
                lbl = f"ov{n} {o.get('template', '')}"
            base.convert("RGB").save(f)
        except (subprocess.CalledProcessError, LookupError, OSError):
            Image.new("RGB", (CELL_W, CELL_H), (40, 40, 40)).save(f)
            lbl = f"ov{n} {o.get('template', '')}"
        cells.append((lbl, f))
    return {"sheets": _paged(cells, out_dir, f"overlays_{timeline}")}


def _strip_sheets(strips: list[tuple[str, Path]], out_dir: Path, per: int = 6) -> list[dict]:
    res, font = [], ImageFont.load_default()
    for n in range(0, len(strips), per):
        page = strips[n:n + per]
        sheet = Image.new("RGB", (STRIP_W, per * ROW_H), (0, 0, 0))
        d = ImageDraw.Draw(sheet)
        for r, (lbl, sp) in enumerate(page):
            im = Image.open(sp).convert("RGB")
            im.thumbnail((STRIP_W, ROW_H))
            sheet.paste(im, (0, r * ROW_H))
            _label(d, 0, r * ROW_H, lbl, font)
        p = Path(out_dir) / f"inventory_{n // per + 1}.png"
        sheet.save(p)
        res.append({"path": str(p), "items": [lbl for lbl, _ in page]})
    return res


def inventory(folder: Path, out_dir: Path, max_clips: int | None = None) -> dict:
    """Probe every video under `folder` (subfolders too, any extension case), make a 6-frame strip per clip,
    tile the strips 6 per sheet. Clips are labelled by path relative to `folder`; unreadable files go in `skipped`."""
    out_dir, folder = Path(out_dir), Path(folder)
    files = sorted((p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXT),
                   key=lambda p: p.relative_to(folder).as_posix().lower())
    if max_clips:
        files = files[:max_clips]
    clips, strips, skipped = [], [], []
    w = STRIP_W // 6
    for p in files:
        rel = p.relative_to(folder).as_posix()
        i = len(clips) + 1
        try:
            info = pt.probe_media(str(p))
            d = info["duration"] or 0
            frames = [Image.open(grab(str(p), d * (k + 0.5) / 6, out_dir / "frames" / f"i{i}_{k}.png", w)).convert("RGB")
                      for k in range(6)]
        except Exception as e:  # ffprobe/ffmpeg failure: report, keep going
            skipped.append({"rel": rel, "path": str(p), "error": str(e)[:200]})
            continue
        strip = Image.new("RGB", (w * 6, max(f.height for f in frames)))
        for k, f in enumerate(frames):
            strip.paste(f, (k * w, 0))
        sp = out_dir / "strips" / f"{i:04d}.png"
        sp.parent.mkdir(parents=True, exist_ok=True)
        strip.save(sp)
        clips.append({"path": str(p), "rel": rel, **{k: info[k] for k in ("duration", "fps", "width", "height", "rotation")},
                      "strip": str(sp)})
        strips.append((f"{i} {rel}", sp))
    return {"clips": clips, "skipped": skipped, "sheets": _strip_sheets(strips, out_dir)}


def main(argv: list[str]) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")   # Windows consoles default to cp1252
    if not argv:
        sys.exit(__doc__)
    cmd, rest = argv[0], argv[1:]
    mx = None
    if "--max" in rest:
        i = rest.index("--max")
        mx = int(rest[i + 1])
        del rest[i:i + 2]
    ai = "--ai" in rest
    args = [a for a in rest if a != "--ai"]
    if cmd == "clips":
        r = clip_sheets(json.loads(Path(args[0]).read_text(encoding="utf-8")), args[1], Path(args[2]), ai)
    elif cmd == "overlays":
        r = overlay_sheets(json.loads(Path(args[0]).read_text(encoding="utf-8")), args[1], Path(args[2]))
    elif cmd == "inventory":
        r = inventory(Path(args[0]), Path(args[1]), mx)
    else:
        sys.exit(__doc__)
    print(json.dumps(r, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
