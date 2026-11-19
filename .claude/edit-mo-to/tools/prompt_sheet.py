"""prompt_sheet.py - one page with every generation prompt of a job, for copy-paste.

usage:
    prompt_sheet.py "<video folder>" [--prompts prompts2.json ...] [--script script.txt] [--timings vo.json]
                    [--title "<title>"] [--out prompt_sheet.html]

Reads <video folder>/storyboard/storyboard.json (character sheets + keyframes) when it exists and any number of
prompts2.json specs (one Clips group per spec / timeline). Each prompt is a card with Copy prompt, Done and
Show prompt; client clips only appear in the running order. The Copy text is exactly the checked text:
plan_tools._block for spec prompts, the beat / character `prompt` for the storyboard.
Default --out: {tmp}/reports/<folder name>/prompt_sheet.html. Prints the written path; exit 2 when there is
nothing to show.
"""
from __future__ import annotations

import html as _html
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import generators as gens  # noqa: E402
import plan_tools as pt  # noqa: E402
from machine import TMP  # noqa: E402
from media_timing import to_sf  # noqa: E402

FPS = pt.FPS


def _vo(p: dict) -> str:
    i, o = p.get("vo_in_f"), p.get("vo_out_f")
    return f"{to_sf(i / FPS)} – {to_sf(o / FPS)}" if isinstance(i, int) and isinstance(o, int) else ""


def _length(p: dict) -> str:
    i, o = p.get("vo_in_f"), p.get("vo_out_f")
    s = f"{(o - i) / FPS:.2f} s" if isinstance(i, int) and isinstance(o, int) else ""
    if p.get("gen_len_s") is not None:
        s += (" · " if s else "") + f"generate {p['gen_len_s']} s"
    return s


def _line(script_lines: list[str], p: dict) -> str:
    n = p.get("line")
    if isinstance(n, str):
        return n
    return pt._line_text(script_lines, p) or ""


def _attach_chips(spec: dict, p: dict) -> list[str]:
    att = spec.get("attach", {}) or {}
    return [f"{a} = {Path(str(att[a])).name}" if a in att else a for a in p.get("attach", [])]


def _sb_card(item: dict, kind: str) -> dict:
    chips = [f"Save as {item['id']}.png"]
    if item.get("status") == "changed":
        chips.append("changed")
    return {"id": item["id"], "title": pt._plain(item["id"]) if kind == "keyframe" else
            f"{pt._plain(item['id'])} · {item.get('name', '')}".rstrip(" ·"),
            "line": item.get("line") if isinstance(item.get("line"), str) else "", "en": item.get("en", ""),
            "vo": "", "length": "", "chips": chips, "copy": item["prompt"], "kind": kind}


def _spec_card(spec: dict, p: dict, script_lines: list[str], gen_label: str) -> dict:
    kind = pt._kind(p)
    chips = _attach_chips(spec, p)
    chips.append(f"Save as {p['id']}.png" if kind in pt.IMAGE_KINDS else f"Save as {p['id']}….mp4")
    if p.get("optional"):
        chips.append("optional")
    if p.get("use"):
        chips.append(f"use {p['use']}")
    if p.get("note"):
        chips.append(str(p["note"]))
    return {"id": str(p["id"]), "title": pt._plain(p["id"]), "line": _line(script_lines, p), "en": "",
            "vo": _vo(p), "length": _length(p), "gen": gen_label if kind == "video" else "",
            "chips": chips, "copy": pt._block(spec, p), "kind": kind}


def _sorted_rows(spec: dict) -> list[dict]:
    rows = [p for p in spec.get("prompts", []) if pt._kind(p) in ("video", pt.CLIENT)]
    if spec.get("style") == "product-ad" and all(isinstance(p.get("at_f"), int) for p in rows):
        return sorted(rows, key=lambda p: p["at_f"])
    if spec.get("style") == "product-ad":
        return rows
    return sorted(rows, key=lambda p: (p["line"] if isinstance(p.get("line"), int) else 10 ** 6, p.get("vo_in_f") or 0))


def collect(folder: Path, specs: list[Path], script_lines: list[str], timings: dict | None) -> dict:
    """Everything the page shows, as plain data (see render)."""
    folder = Path(folder)
    data: dict = {"characters": [], "keyframes": [], "waiting_keyframes": [], "groups": [], "order": [],
                  "setup": [], "title": ""}
    board_ids: set[str] = set()
    sb = folder / "storyboard" / "storyboard.json"
    if sb.exists():
        board = json.loads(sb.read_text(encoding="utf-8"))
        data["title"] = board.get("title", "")
        if board.get("direction"):
            data["setup"].append(["Direction", board["direction"]])
        for c in board.get("characters") or []:
            if c.get("prompt"):
                data["characters"].append(_sb_card(c, "character"))
                board_ids.add(c["id"])
        for b in board.get("beats") or []:
            if b.get("prompt"):
                data["keyframes"].append(_sb_card(b, "keyframe"))
                board_ids.add(b["id"])
            elif (b.get("shot") or {}).get("type") != "client":
                data["waiting_keyframes"].append(b.get("id"))
    for path in specs:
        spec = json.loads(Path(path).read_text(encoding="utf-8"))
        title = spec.get("job") or (Path(path).parent.name if len(specs) > 1 else "Clips")
        gen_label = gens.for_spec(spec)["label"] if spec.get("generator") else ""
        for p in spec.get("prompts", []):   # image prompts from the spec, unless the storyboard has that id
            if pt._kind(p) in pt.IMAGE_KINDS and str(p["id"]) not in board_ids:
                dest = data["characters"] if pt._kind(p) == "character" else data["keyframes"]
                dest.append(_spec_card(spec, p, script_lines, gen_label))
                board_ids.add(str(p["id"]))
        cards = []
        for p in _sorted_rows(spec):
            row = {"n": len(data["order"]) + 1, "id": str(p["id"]), "group": title, "line": _line(script_lines, p),
                   "vo": _vo(p), "client": pt._kind(p) == pt.CLIENT}
            if row["client"]:
                fps = round(p.get("fps", FPS))
                cut = (f"{to_sf(p['in_f'] / fps, fps)}–{to_sf(p['out_f'] / fps, fps)}"
                       if isinstance(p.get("in_f"), int) and isinstance(p.get("out_f"), int) else "")
                row["source"] = f"Client clip {Path(str(p.get('file', ''))).name}" + (f" · cut {cut}" if cut else "")
            else:
                cards.append(_spec_card(spec, p, script_lines, gen_label))
                row["source"] = f"Generate · {gen_label}" if gen_label else "Generate"
            data["order"].append(row)
        if cards:
            data["groups"].append({"title": title, "cards": cards})
        setup = [["Generator", gen_label]] if gen_label else []
        if spec.get("aspect"):
            setup.append(["Aspect", spec["aspect"]])
        att = spec.get("attach") or {}
        if att:
            setup.append(["Attach", "; ".join(f"{k} = {v}" for k, v in att.items())])
        notes = spec.get("notes")
        for n in ([notes] if isinstance(notes, str) else notes or []):
            setup.append(["Note", n])
        if setup and len(specs) > 1:
            data["setup"].append([f"— {title} —", ""])
        data["setup"] += setup
    return data


def _count(data: dict) -> int:
    return len(data["characters"]) + len(data["keyframes"]) + sum(len(g["cards"]) for g in data["groups"])


def render(data: dict, title: str, job: str) -> str:
    """The self-contained HTML page. The data is embedded as JSON with every '<' escaped."""
    blob = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    key = json.dumps("promptsheet:" + job).replace("<", "\\u003c")
    t = _html.escape(title)
    return TEMPLATE.replace("{{TITLE}}", t).replace("{{DATA}}", blob).replace("{{KEY}}", key)


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{TITLE}}</title>
<style>
:root{--bg:#f6f5f2;--card:#fff;--ink:#17171a;--mute:#6b6b73;--line:#e3e1dc;--acc:#2f5bea;--acc-ink:#fff;--chip:#efeee9;--ok:#1f8a4c;--warn:#b35c00;--pre:#f3f2ee}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#121214;--card:#1c1c20;--ink:#ecebe8;--mute:#9a9aa3;--line:#2c2c32;--acc:#7c9bff;--acc-ink:#0d0d10;--chip:#26262c;--ok:#4cc27f;--warn:#f0a050;--pre:#16161a}}
:root[data-theme="dark"]{--bg:#121214;--card:#1c1c20;--ink:#ecebe8;--mute:#9a9aa3;--line:#2c2c32;--acc:#7c9bff;--acc-ink:#0d0d10;--chip:#26262c;--ok:#4cc27f;--warn:#f0a050;--pre:#16161a}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
header{padding:28px 16px 8px;max-width:880px;margin:0 auto}
h1{font-size:22px;margin:0 0 4px;letter-spacing:-.01em}
.sub{color:var(--mute);font-size:13px}
nav{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line)}
nav .in{max-width:880px;margin:0 auto;padding:8px 16px;display:flex;gap:6px;overflow-x:auto;align-items:center}
nav a{white-space:nowrap;text-decoration:none;color:var(--ink);background:var(--chip);padding:5px 11px;border-radius:999px;font-size:13px}
nav .prog{margin-left:auto;white-space:nowrap;color:var(--mute);font-size:13px;padding-left:8px}
main{max-width:880px;margin:0 auto;padding:8px 16px 80px}
section{margin-top:28px;scroll-margin-top:56px}
h2{font-size:17px;margin:0 0 10px}
h3{font-size:14px;margin:18px 0 8px;color:var(--mute);font-weight:600;text-transform:uppercase;letter-spacing:.04em}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;margin:0 0 10px;overflow:hidden;scroll-margin-top:56px}
.card.done{opacity:.55}
.head{display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center;padding:10px 14px;border-bottom:1px solid var(--line)}
.cid{font-weight:700}
.meta{color:var(--mute);font-size:13px}
.chips{display:flex;flex-wrap:wrap;gap:4px}
.chip{background:var(--chip);border-radius:6px;padding:1px 7px;font-size:12px;color:var(--mute)}
.chip.flag{color:var(--warn)}
.body{padding:10px 14px 12px}
.line{font-size:15px;margin:0 0 8px}
.line .en{display:block;color:var(--mute);font-size:13px}
.actions{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
button.copy{background:var(--acc);color:var(--acc-ink);border:0;border-radius:8px;padding:8px 16px;font:600 14px/1 inherit;cursor:pointer}
button.copy.ok{background:var(--ok)}
label.done{display:flex;gap:6px;align-items:center;font-size:14px;color:var(--mute);cursor:pointer}
details{margin-top:8px}
summary{cursor:pointer;color:var(--mute);font-size:13px}
pre{white-space:pre-wrap;word-break:break-word;background:var(--pre);border:1px solid var(--line);border-radius:8px;padding:10px 12px;font:12.5px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;margin:8px 0 0;max-height:420px;overflow:auto}
.note{color:var(--mute);font-size:13px;margin:0 0 10px}
.tablewrap{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:12px}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--mute);font-weight:600}
td.mono{font-family:ui-monospace,Menlo,Consolas,monospace;white-space:nowrap}
tr.client td{color:var(--mute)}
a{color:var(--acc)}
dl{display:grid;grid-template-columns:max-content 1fr;gap:4px 14px;margin:0;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;font-size:13px}
dt{color:var(--mute)}dd{margin:0;word-break:break-word}
#toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%) translateY(20px);opacity:0;background:var(--ink);color:var(--bg);padding:8px 14px;border-radius:8px;font-size:14px;transition:.2s;pointer-events:none}
#toast.show{opacity:1;transform:translateX(-50%)}
</style></head>
<body>
<header><h1>{{TITLE}}</h1><div class="sub" id="sub"></div></header>
<nav><div class="in" id="nav"></div></nav>
<main id="main"></main>
<div id="toast" role="status" aria-live="polite"></div>
<script>
const DATA = {{DATA}};
const KEY = {{KEY}};
const $ = (s, el=document) => el.querySelector(s);
const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
let done = {};
try { done = JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch (e) {}
function save(){ try { localStorage.setItem(KEY, JSON.stringify(done)); } catch (e) {} }
function toast(m){ const t=$("#toast"); t.textContent=m; t.classList.add("show"); clearTimeout(t._h); t._h=setTimeout(()=>t.classList.remove("show"),1600); }
async function copy(text, pre, btn){
  try { await navigator.clipboard.writeText(text); toast("Copied"); btn.classList.add("ok"); btn.textContent="Copied ✓"; setTimeout(()=>{btn.classList.remove("ok");btn.textContent="Copy prompt";},1500); }
  catch (e) { const r=document.createRange(); r.selectNodeContents(pre); const s=getSelection(); s.removeAllRanges(); s.addRange(r); toast("Press Ctrl/Cmd+C to copy the selected prompt"); }
}
const all = [...DATA.characters, ...DATA.keyframes, ...DATA.groups.flatMap(g => g.cards)];
function progress(){ const n = all.filter(c => done[c.kind+":"+c.id]).length; $("#prog").textContent = n + " / " + all.length + " done"; }
function card(c){
  const el = document.createElement("article"); el.className = "card"; el.id = "p-" + c.kind + "-" + c.id;
  const k = c.kind + ":" + c.id;
  const chips = (c.chips||[]).map(x => `<span class="chip${/flag|changed/.test(x)?" flag":""}">${esc(x)}</span>`).join("");
  const meta = [c.vo && ("VO " + c.vo), c.length, c.gen].filter(Boolean).map(esc).join(" · ");
  el.innerHTML = `<div class="head"><span class="cid">${esc(c.title)}</span>${meta?`<span class="meta">${meta}</span>`:""}<div class="chips">${chips}</div></div>
  <div class="body">${c.line?`<p class="line">${esc(c.line)}${c.en?`<span class="en">${esc(c.en)}</span>`:""}</p>`:""}
  <div class="actions"><button class="copy" type="button">Copy prompt</button><label class="done"><input type="checkbox"> Done</label></div>
  <details><summary>Show prompt</summary><pre></pre></details></div>`;
  const pre = $("pre", el); pre.textContent = c.copy;
  const btn = $("button", el); btn.addEventListener("click", () => { $("details", el).open = true; copy(c.copy, pre, btn); });
  const cb = $("input", el); cb.checked = !!done[k]; el.classList.toggle("done", cb.checked);
  cb.addEventListener("change", () => { done[k] = cb.checked; el.classList.toggle("done", cb.checked); save(); progress(); });
  return el;
}
const main = $("#main"), nav = $("#nav"), links = [];
function section(id, title, note){ const s=document.createElement("section"); s.id=id; s.innerHTML=`<h2>${esc(title)}</h2>${note?`<p class="note">${esc(note)}</p>`:""}`; main.appendChild(s); links.push([id,title]); return s; }
if (DATA.setup.length){ const s=section("setup","Setup"); const dl=document.createElement("dl");
  dl.innerHTML = DATA.setup.map(([k,v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join(""); s.appendChild(dl); }
if (DATA.characters.length){ const s=section("characters","Character sheets","Generate these first and save each as its Save-as name."); DATA.characters.forEach(c=>s.appendChild(card(c))); }
if (DATA.keyframes.length || DATA.waiting_keyframes.length){
  const s=section("keyframes","Storyboard keyframes", DATA.waiting_keyframes.length && !DATA.keyframes.length ? "The keyframe prompts come after the character sheet is saved." : "");
  DATA.keyframes.forEach(c=>s.appendChild(card(c)));
  if (DATA.waiting_keyframes.length && DATA.keyframes.length){ const p=document.createElement("p"); p.className="note"; p.textContent="Still waiting for a prompt: "+DATA.waiting_keyframes.join(", "); s.appendChild(p); }
}
if (DATA.groups.length){ const s=section("clips","Clip prompts");
  DATA.groups.forEach(g => { if (DATA.groups.length>1){ const h=document.createElement("h3"); h.textContent=g.title; s.appendChild(h);} g.cards.forEach(c=>s.appendChild(card(c))); }); }
if (DATA.order.length){ const s=section("order","Running order"); const multi = new Set(DATA.order.map(r=>r.group)).size>1;
  const w=document.createElement("div"); w.className="tablewrap";
  w.innerHTML = `<table><thead><tr><th>#</th><th>Clip</th>${multi?"<th>Timeline</th>":""}<th>VO</th><th>Script line</th><th>Source</th></tr></thead><tbody>${
    DATA.order.map(r => `<tr class="${r.client?"client":""}"><td class="mono">${r.n}</td><td class="mono">${r.client?esc(r.id):`<a href="#p-video-${esc(r.id)}">${esc(r.id)}</a>`}</td>${multi?`<td>${esc(r.group)}</td>`:""}<td class="mono">${esc(r.vo)}</td><td>${esc(r.line)}</td><td>${esc(r.source)}</td></tr>`).join("")}</tbody></table>`;
  s.appendChild(w); }
nav.innerHTML = links.map(([id,t]) => `<a href="#${id}">${esc(t)}</a>`).join("") + `<span class="prog" id="prog"></span>`;
$("#sub").textContent = all.length + " prompts · Copy gives the exact prompt · Done ticks are saved in this browser only";
progress();
</script>
</body></html>
"""


def main(argv: list[str]) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not argv or argv[0] in ("-h", "--help"):
        raise SystemExit(__doc__)
    folder = Path(argv[0])
    args = argv[1:]
    specs: list[Path] = []
    opts: dict[str, str] = {}
    i = 0
    while i < len(args):
        if args[i] == "--prompts":
            specs.append(Path(args[i + 1]))
        elif args[i] in ("--script", "--timings", "--title", "--out"):
            opts[args[i]] = args[i + 1]
        else:
            raise SystemExit(f"unknown argument {args[i]!r}\n{__doc__}")
        i += 2
    lines = ([l for l in Path(opts["--script"]).read_text(encoding="utf-8").splitlines() if l.strip()]
             if "--script" in opts else [])
    timings = json.loads(Path(opts["--timings"]).read_text(encoding="utf-8")) if "--timings" in opts else None
    data = collect(folder, specs, lines, timings)
    if not _count(data):
        print("no prompts to show: no storyboard prompts and no --prompts spec with prompts", file=sys.stderr)
        raise SystemExit(2)
    title = opts.get("--title") or data["title"] or f"{folder.name} · Prompt sheet"
    out = Path(opts.get("--out") or Path(TMP) / "reports" / folder.name / "prompt_sheet.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(data, title, folder.name), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main(sys.argv[1:])
