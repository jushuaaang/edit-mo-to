"""Storyboard sheet for the script gate: see the direction of the whole ad before any video is generated.

CLI (prints a short JSON summary):
    storyboard.py <storyboard.json> [--out <folder>]

The style agent writes storyboard.json (mode: storyboard). One beat per script line or cut:
    {"title": "Fascora · Hook 1", "direction": "2–3 lines: hook idea, pacing, look",
     "font": "Inter", "bg": "#0e2f5a", "fg": "#ffffff", "accent": "#8fd3ff",    (sheet colours, from the brand)
     "beats": [{"id": "SB-1", "line": "script words", "est": "0:00–2:10",
                "shot": {"type": "client", "file": "D:/…/clip.mp4", "t": 12.4}
                     or {"type": "ai", "framing": "Close-up", "subject": "…", "action": "…", "camera": "slow push-in"},
                "graphic": {"template": "big-text", "vars": {…}, "duration": 2.5},   (optional, from CATALOGUE)
                "transition": "whip blur", "note": "mood, music, SFX"}]}

Pictures: client shots use the real frame at `t`. AI shots use the editor's keyframe <out>/SB-n.(png|jpg|webp)
when it exists (generated in Nano Banana from the storyboard prompts), otherwise a shot card. Graphics are
rendered with the real templates and composited where they will sit. Writes <out>/storyboard.html, one
self-contained page (images embedded) that can be sent to a client.
"""
import base64
import hashlib
import html
import json
import subprocess
import sys
from pathlib import Path

W, H = 1080, 1920
PANEL_W = 432
KEY_EXT = (".png", ".jpg", ".jpeg", ".webp")
FILL = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"


def _ff(*args):
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *map(str, args)], check=True)


def keyframe(out: Path, beat_id: str) -> Path | None:
    for ext in KEY_EXT:
        p = out / f"{beat_id}{ext}"
        if p.exists():
            return p
    return None


def base_frame(beat: dict, out: Path, work: Path) -> tuple[Path | None, str]:
    """The panel's picture at full canvas size, and where it came from (client / keyframe / card)."""
    shot = beat.get("shot") or {}
    dst = work / f"{beat['id']}_base.png"
    if shot.get("type") == "client" and shot.get("file") and Path(shot["file"]).exists():
        _ff("-ss", f"{float(shot.get('t', 0)):.3f}", "-i", shot["file"], "-frames:v", 1, "-vf", FILL, dst)
        return dst, "client"
    k = keyframe(out, beat["id"])
    if k:
        _ff("-i", k, "-frames:v", 1, "-vf", FILL, dst)
        return dst, "keyframe"
    return None, "card"


def graphic_mov(g: dict, cache: Path) -> Path:
    """Render a template once per (template, vars); reused on re-runs and by the build if vars match."""
    import motion_render as mr

    variables = dict(g.get("vars") or {})
    variables.setdefault("duration", g.get("duration", 2.5))
    key = hashlib.sha1(json.dumps([g["template"], variables], sort_keys=True).encode()).hexdigest()[:14]
    mov = cache / f"{g['template']}_{key}.mov"
    if not mov.exists():
        cache.mkdir(parents=True, exist_ok=True)
        mr.render(g["template"], mov, variables)
    return mov


def panel(beat: dict, out: Path, work: Path, cache: Path, render_graphics: bool = True) -> tuple[Path, str]:
    base, source = base_frame(beat, out, work)
    if base is None:  # shot card: neutral backdrop, the card text is laid over it in HTML
        base = work / f"{beat['id']}_card.png"
        _ff("-f", "lavfi", "-i", f"color=c=0x2a2c31:s={W}x{H}", "-frames:v", 1, base)
    g = beat.get("graphic")
    final = work / f"{beat['id']}.jpg"
    if g and g.get("template") and render_graphics:
        mov = graphic_mov(g, cache)
        dur = float((g.get("vars") or {}).get("duration", g.get("duration", 2.5)))
        # grab the graphic's frame on its own first: seeking a ProRes input inside an overlay graph
        # can hand the filter no overlay frame, which silently drops the graphic
        still = work / f"{beat['id']}_graphic.png"
        _ff("-ss", f"{dur * 0.55:.3f}", "-i", mov, "-frames:v", 1, "-pix_fmt", "rgba", still)
        _ff("-i", base, "-i", still, "-filter_complex", f"[0][1]overlay,scale={PANEL_W}:-2", "-frames:v", 1,
            "-q:v", 4, final)
    else:
        _ff("-i", base, "-vf", f"scale={PANEL_W}:-2", "-q:v", 4, final)
    return final, source


def _img(p: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode()


def _e(s) -> str:
    return html.escape(str(s or ""))


def page(sb: dict, panels: list[tuple[dict, Path, str]]) -> str:
    font, bg, fg, acc = (sb.get(k) for k in ("font", "bg", "fg", "accent"))
    font = font or "Inter"
    cards = []
    for beat, img, source in panels:
        shot, g = beat.get("shot") or {}, beat.get("graphic") or {}
        if shot.get("type") == "client":
            shot_txt = _e(f"Client clip · {Path(shot.get('file', '')).name} @ {shot.get('t', 0)}s")
        else:
            shot_txt = " · ".join(_e(shot.get(k)) for k in ("framing", "subject", "action", "camera") if shot.get(k))
        card = ""
        if source == "card":
            card = (f'<div class="card"><b>{_e(shot.get("framing") or "AI shot")}</b>'
                    f'<span>{_e(shot.get("subject"))}</span><span>{_e(shot.get("action"))}</span>'
                    f'<i>{_e(shot.get("camera"))}</i><em>AI · keyframe not made yet</em></div>')
        tag = {"client": "CLIENT", "keyframe": "AI · KEYFRAME", "card": "AI · SHOT CARD"}[source]
        rows = [f'<div class="sh">{shot_txt}</div>'] if source != "card" else []
        if g.get("template"):
            rows.append(f'<div class="meta">Graphic: {_e(g["template"])}</div>')
        if beat.get("transition"):
            rows.append(f'<div class="meta">Cut: {_e(beat["transition"])}</div>')
        if beat.get("note"):
            rows.append(f'<div class="meta">{_e(beat["note"])}</div>')
        cards.append(f'''<figure><div class="pic"><img src="{_img(img)}" alt="{_e(beat["id"])}">{card}
<span class="tag">{tag}</span></div><figcaption><div class="hd"><b>{_e(beat["id"])}</b><span>{_e(beat.get("est"))}</span></div>
<q>{_e(beat.get("line"))}</q>{"".join(rows)}</figcaption></figure>''')
    missing = [b["id"] for b, _, s in panels if s == "card"]
    status = (f"{len(missing)} AI shot(s) still shown as cards: {', '.join(missing)}. Generate their keyframes from the "
              f"storyboard prompts, save them in this folder as SB-n.png, and re-run." if missing else "All shots have pictures.")
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(sb.get("title") or "Storyboard")}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family={_e(font).replace(" ", "+")}:wght@400;600;700&display=swap">
<style>
:root{{--bg:#f4f4f6;--ink:#141416;--mut:#6b6b73;--line:#dcdce2;--brand:{_e(bg or "#141416")};--on:{_e(fg or "#ffffff")};--acc:{_e(acc or "#3b82f6")}}}
@media (prefers-color-scheme:dark){{:root{{--bg:#111113;--ink:#f1f1f3;--mut:#9a9aa3;--line:#2c2c31}}}}
*{{box-sizing:border-box;margin:0}}body{{background:var(--bg);color:var(--ink);font-family:"{_e(font)}",system-ui,sans-serif;padding:24px 16px}}
header{{max-width:1400px;margin:0 auto 20px;background:var(--brand);color:var(--on);border-radius:18px;padding:20px 24px}}
h1{{font-size:26px}}header p{{margin-top:8px;line-height:1.45;opacity:.9;max-width:900px}}header small{{display:block;margin-top:10px;opacity:.75}}
main{{max-width:1400px;margin:0 auto;display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:18px}}
figure{{background:color-mix(in srgb,var(--bg) 70%,#fff 30%);border:1px solid var(--line);border-radius:16px;overflow:hidden}}
.pic{{position:relative;aspect-ratio:9/16;background:#2a2c31}}.pic img{{width:100%;height:100%;object-fit:cover;display:block}}
.tag{{position:absolute;top:8px;left:8px;font-size:10px;font-weight:700;letter-spacing:.08em;background:rgba(0,0,0,.6);color:#fff;padding:4px 7px;border-radius:6px}}
.card{{position:absolute;inset:auto 8% 7%;background:rgba(0,0,0,.55);border-radius:12px;padding:10px 8px;display:flex;flex-direction:column;gap:6px;color:#fff;text-align:center;font-size:14px;line-height:1.35}}
.card b{{font-size:20px;color:var(--acc)}}.card i{{opacity:.8}}.card em{{margin-top:8px;font-size:11px;opacity:.6;font-style:normal}}
figcaption{{padding:12px 14px 14px;display:flex;flex-direction:column;gap:6px;font-size:13px;line-height:1.4}}
.hd{{display:flex;justify-content:space-between;color:var(--mut);font-size:12px}}.hd b{{color:var(--ink)}}
q{{font-weight:600;font-size:14px}}.sh,.meta{{color:var(--mut)}}
</style></head><body>
<header><h1>{_e(sb.get("title") or "Storyboard")}</h1><p>{_e(sb.get("direction"))}</p><small>{_e(status)}</small></header>
<main>{"".join(cards)}</main></body></html>'''


def build(sb: dict, out: Path, render_graphics: bool = True) -> dict:
    import shutil
    import tempfile

    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="emt-sb-"))
    try:
        from machine import TMP
        cache = TMP / "storyboard_graphics"
    except Exception:
        cache = work / "graphics"
    panels = []
    for beat in sb["beats"]:
        img, source = panel(beat, out, work, cache, render_graphics)
        panels.append((beat, img, source))
    html_path = out / "storyboard.html"
    html_path.write_text(page(sb, panels), encoding="utf-8")  # images are embedded, so the frames can go
    shutil.rmtree(work, ignore_errors=True)
    return {"html": str(html_path), "panels": len(panels),
            "keyframes_missing": [b["id"] for b, _, s in panels if s == "card"]}


def main(argv: list[str]) -> None:
    argv = list(argv)
    out = None
    if "--out" in argv:
        i = argv.index("--out")
        out = Path(argv[i + 1])
        del argv[i:i + 2]
    src = Path(argv[0])
    sb = json.loads(src.read_text(encoding="utf-8"))
    print(json.dumps(build(sb, out or src.parent), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main(sys.argv[1:])
