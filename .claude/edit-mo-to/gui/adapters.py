"""Tool outputs -> one generic table the GUI renders, so the GUI never knows each tool's format.

ADAPTERS maps a name to a function taking the tool's parsed JSON and returning
    {"title": str, "columns": [str], "rows": [{"id": str, "cells": [str], "status": ..., "note": str|None}]}
status is "ok" | "wait" | "you" | "err" | "opt" | "mute" | None.

  timings  media_timing.py vo JSON (lines[]: line,start_sf,end_sf,matched)
  cuts     speech_cuts.py propose JSON (candidates[])
  qa       qa_check.py JSON (rows[], passed, verdict)
  clips    qc_clips.py report.json (clips[])
  prompts  plan_tools.py prompts2.json (prompts[])

Used by `job.py output --from <adapter> <tool-output-path>`. Standard library only, plus plan_tools (tools/) for the
prompt text, so a prompt row carries the same text the chat shows.
"""
import sys
from pathlib import Path
from typing import Callable

TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

QA_STATUS = {"PASS": "ok", "FAIL": "err", "FLAG": "err", "OPEN": "you"}


def _s(value) -> str:
    return "" if value is None else str(value)


def _table(title: str, columns: list[str], rows: list[dict]) -> dict:
    return {"title": title, "columns": columns, "rows": rows}


def _row(id_, cells: list, status: str | None, note: str | None = None) -> dict:
    return {"id": _s(id_), "cells": [_s(c) for c in cells], "status": status, "note": note or None}


def _sf(seconds) -> str:
    """seconds:frames at 30 fps, as media_timing.to_sf (kept local so the GUI needs no tools import)."""
    secs, ff = divmod(round(float(seconds) * 30), 30)
    return f"{secs}:{ff:02d}" if secs < 60 else f"{secs // 60}:{secs % 60:02d}:{ff:02d}"


def timings(data: dict) -> dict:
    rows = [_row(i, [i, ln.get("line"), ln.get("start_sf"), ln.get("end_sf"),
                     "yes" if ln.get("matched") else "no"],
                 "ok" if ln.get("matched") else "err",
                 None if ln.get("matched") else "line not found in the voiceover; timing is a guess")
            for i, ln in enumerate(data.get("lines") or [], 1)]
    return _table(f"Voiceover timings (total {data.get('total', '?')})",
                  ["#", "Line", "In", "Out", "Match"], rows)


def cuts(data: dict) -> dict:
    rows = []
    for c in data.get("candidates") or []:
        a, b = c.get("cut") or [0, 0]
        what = c.get("note") or " -> ".join(x for x in (c.get("removes"), c.get("keeps")) if x)
        rows.append(_row(c.get("id"), [c.get("id"), c.get("type"), _sf(a), _sf(b), what, c.get("recommend")],
                         "ok" if c.get("recommend") == "cut" else "you"))
    return _table(f"Proposed cuts ({_sf(data.get('duration', 0))} source)",
                  ["Id", "Type", "From", "To", "What", "Recommend"], rows)


def qa(data: dict) -> dict:
    rows = [_row(r.get("n", i), [r.get("check"), r.get("evidence"), r.get("fix"), r.get("timeline")],
                 QA_STATUS.get(str(r.get("status")).upper(), "mute"))
            for i, r in enumerate(data.get("rows") or [], 1)]
    return _table(f"QA: {data.get('verdict', '?')}", ["Check", "Evidence", "Fix", "Timeline"], rows)


def clips(data: dict) -> dict:
    """Extra row fields: `match` (the expected clip name it matched, or None) and `sheet` (qc_clips' contact
    sheet, <images>/<stem>_sheet.jpg, when the report names its images folder)."""
    rows, images = [], data.get("images")
    for c in data.get("clips") or []:
        m = c.get("match") or {}
        match = m.get("name") or m.get("why") or "-"
        flags = "; ".join(c.get("flags") or []) or "-"
        row = _row(c.get("file"), [c.get("file"), match, c.get("status"), flags],
                   "ok" if c.get("status") == "PASS" else "err", c.get("action"))
        row["match"] = m.get("name") or None
        stem = Path(_s(c.get("file"))).stem
        row["sheet"] = f"{str(images).rstrip('/')}/{stem}_sheet.jpg" if images and stem else None
        rows.append(row)
    return _table(f"Clip QC {data.get('batch', '')}".strip(), ["File", "Match", "Result", "Flags"], rows)


def prompts(data: dict) -> dict:
    """Extra row field `prompt`: the full prompt exactly as the chat deliverable shows it (plan_tools._block, the
    fenced block per prompt in render_prompts); None for a picked client clip, which has no prompt."""
    import plan_tools  # the one renderer of prompt text (kept lazy: only this adapter needs the tools)
    rows = []
    for p in data.get("prompts") or []:
        vo = f"{p['vo_in_f']}-{p['vo_out_f']}f" if "vo_in_f" in p and "vo_out_f" in p else ""
        what = p.get("action") or p.get("subject") or ""
        row = _row(p.get("id"), [p.get("id"), p.get("line"), vo, p.get("gen_len_s"), what, p.get("dialogue")], None)
        row["prompt"] = None if plan_tools._kind(p) == plan_tools.CLIENT else plan_tools._block(data, p)
        rows.append(row)
    return _table("Generation prompts", ["Id", "Line", "VO span", "Length (s)", "Shot", "Dialogue"], rows)


ADAPTERS: dict[str, Callable[[dict], dict]] = {
    "timings": timings, "cuts": cuts, "qa": qa, "clips": clips, "prompts": prompts}
