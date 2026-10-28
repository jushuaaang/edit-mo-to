"""Plan usage for the dashboard (spec "Beginner friendly": Token usage, Usage read automatically, Manual fallback).

Three sources, all read-only:
  {tmp}/gui/usage.json     the plan's week and 5-hour % that gui/statusline.py saves (read_auto)
  job.json "usage"         the week % at each job's start and finish (job.py usage-mark; per_video_pct)
  Claude Code's logs       ~/.claude/projects/<project_log_name(root)>/ (CLAUDE_CONFIG_DIR wins): the main *.jsonl
                           and the helpers' logs in subfolders. Only each message's `timestamp`, `message.id` and
                           `message.usage` numbers are kept; text is never stored or returned (entries, tokens). This
                           is the one read outside {root} and {tmp}, and only for the {root} project folder.
  prefs "usage_readings"   the weekly % the editor typed from /usage (manual), used only when usage.json is missing,
                           old or without the week

report(root, gui) is GET /api/usage. Every estimate is "about"; missing data is None, never a guess.
"""
import json
import math
import os
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import folders  # noqa: E402
import jobstate as js  # noqa: E402

FRESH_S = 30 * 60          # an automatic reading older than this is "old"
MANUAL_OLD_S = 24 * 3600   # a typed reading older than this asks for a fresh one
WEEK_S = 7 * 86400
RESET_SLACK_S = 3600       # resets_at that moved more than this between start and finish = the week reset
NEED_VIDEOS = 3            # finished videos needed before guessing % per video
FIELDS = (("in", "input_tokens"), ("cw", "cache_creation_input_tokens"), ("cr", "cache_read_input_tokens"),
          ("out", "output_tokens"))

_cache: dict = {}          # log path -> {"size", "mtime", "offset", "entries"}
_cache_lock = threading.Lock()


# ---------- Claude Code's project log folder ----------

def project_log_name(root) -> str:
    """Claude Code's folder name for a project: every character that is not a letter or digit becomes "-"
    ("/Users/me/Video Editing" -> "-Users-me-Video-Editing")."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(root))


def claude_dir() -> Path:
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env) if env else Path.home() / ".claude"


def project_logs(root) -> "Path | None":
    """<claude dir>/projects/<project_log_name(root)>, matched case-insensitively (a Windows drive letter); None when
    there is no such folder (the app then says "Usage not available")."""
    base = claude_dir() / "projects"
    name = project_log_name(root)
    if (base / name).is_dir():
        return base / name
    try:
        for p in base.iterdir():
            if p.name.lower() == name.lower() and p.is_dir():
                return p
    except OSError:
        pass
    return None


# ---------- token entries from the logs (numbers and times only) ----------

def _epoch(text) -> "float | None":
    if not isinstance(text, str) or len(text) > 40:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (dt if dt.tzinfo else dt.astimezone()).timestamp()


def _count(v) -> int:
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else 0


def _parse_lines(data: bytes, helper: bool) -> list:
    out = []
    for raw in data.split(b"\n"):
        if b'"usage"' not in raw:
            continue   # most lines (the editor's messages, tool results) have no usage: not even parsed
        try:
            obj = json.loads(raw)
        except ValueError:
            continue
        msg = obj.get("message") if isinstance(obj, dict) else None
        use = msg.get("usage") if isinstance(msg, dict) else None
        t = _epoch(obj.get("timestamp"))
        if not isinstance(use, dict) or t is None:
            continue
        mid = msg.get("id")
        entry = {"t": t, "id": mid if isinstance(mid, str) and len(mid) <= 100 else None, "helper": helper}
        entry.update({k: _count(use.get(f)) for k, f in FIELDS})
        out.append(entry)
    return out


def _file_entries(path: Path, helper: bool) -> list:
    """The file's entries, cached by size and mtime; a log that only grew is read from where the last read ended."""
    try:
        st = path.stat()
    except OSError:
        return []
    key = str(path)
    with _cache_lock:
        c = _cache.get(key)
    if c and c["size"] == st.st_size and c["mtime"] == st.st_mtime_ns:
        return c["entries"]
    start, kept = (c["offset"], c["entries"]) if c and st.st_size >= c["offset"] else (0, [])
    try:
        with path.open("rb") as f:
            f.seek(start)
            data = f.read()
    except OSError:
        return c["entries"] if c else []
    end = data.rfind(b"\n") + 1          # a half-written last line waits for the next read
    got = kept + _parse_lines(data[:end], helper)
    with _cache_lock:
        _cache[key] = {"size": st.st_size, "mtime": st.st_mtime_ns, "offset": start + end, "entries": got}
    return got


def entries(logs: Path) -> list:
    """Every reply's token numbers in the project's logs, oldest first; a reply written over several lines (one per
    content block, the same message id) counts once."""
    out, seen = [], set()
    try:
        files = sorted(Path(logs).rglob("*.jsonl"))
    except OSError:
        return []
    for p in files:
        for e in _file_entries(p, p.parent != Path(logs)):
            if e["id"]:
                if e["id"] in seen:
                    continue
                seen.add(e["id"])
            out.append(e)
    out.sort(key=lambda e: e["t"])
    return out


def tokens(ents: list, start: float, end: float) -> dict:
    """Token sums for start <= t < end: total, claude (main sessions), helpers (subagents), and per kind."""
    s = {"total": 0, "claude": 0, "helpers": 0, "input": 0, "cache_write": 0, "cache_read": 0, "output": 0}
    for e in ents:
        if start <= e["t"] < end:
            n = e["in"] + e["cw"] + e["cr"] + e["out"]
            s["total"] += n
            s["helpers" if e["helper"] else "claude"] += n
            s["input"] += e["in"]
            s["cache_write"] += e["cw"]
            s["cache_read"] += e["cr"]
            s["output"] += e["out"]
    return s


# ---------- the status line's reading ----------

def _window(data: dict, name: str, now: float) -> "tuple":
    w = data.get(name)
    if not isinstance(w, dict):
        return None, None
    pct, resets = w.get("used_percentage"), w.get("resets_at")
    if not isinstance(pct, (int, float)) or isinstance(pct, bool) or not 0 <= pct <= 100:
        return None, None
    resets = resets if isinstance(resets, (int, float)) and not isinstance(resets, bool) else None
    if resets is not None and resets <= now:
        return None, None    # that window reset since: its % no longer holds
    return pct, resets


def read_auto(gui: Path, now: "float | None" = None) -> "dict | None":
    """{tmp}/gui/usage.json as {"week_pct", "week_resets_at", "five_hour_pct", "five_hour_resets_at", "at", "old"};
    None when missing or unreadable. old: over 30 minutes old, or no week % (missing or reset since)."""
    now = time.time() if now is None else now
    try:
        data = json.loads((Path(gui) / "usage.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    at = _epoch(data.get("at")) if isinstance(data, dict) else None
    if at is None:
        return None
    week, week_resets = _window(data, "seven_day", now)
    five, five_resets = _window(data, "five_hour", now)
    return {"week_pct": week, "week_resets_at": week_resets, "five_hour_pct": five, "five_hour_resets_at": five_resets,
            "at": data["at"], "old": now - at > FRESH_S or week is None}


# ---------- % per video and videos left ----------

def per_video_pct(jobs: list) -> "tuple":
    """(average week % per finished video, how many counted): only jobs with a start and a finish % in the same week
    (resets_at unchanged, finish >= start). The average is None until NEED_VIDEOS count."""
    used = []
    for job in jobs:
        u = job.get("usage") if isinstance(job, dict) else None
        if not isinstance(u, dict):
            continue
        a, b = u.get("start_pct"), u.get("finish_pct")
        if not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (a, b)) or b < a:
            continue
        ra, rb = u.get("start_resets_at"), u.get("finish_resets_at")
        if isinstance(ra, (int, float)) and isinstance(rb, (int, float)) and abs(ra - rb) > RESET_SLACK_S:
            continue
        used.append(b - a)
    if len(used) < NEED_VIDEOS:
        return None, len(used)
    return round(sum(used) / len(used), 1), len(used)


def videos_left(week_pct, per_video) -> "int | None":
    """floor((100 - week %) / % per video), never below 0; None when either is unknown or a video uses 0%."""
    if week_pct is None or not per_video or per_video <= 0:
        return None
    return max(0, math.floor((100 - week_pct) / per_video))


# ---------- the manual fallback ----------

def manual(readings: list, ents: "list | None", now: float) -> dict:
    """From the weekly % the editor typed: the last reading, and (from two or more readings and the tokens between
    them) about how many tokens make 1%, so the estimate grows with the tokens used since. old: no reading, the last
    is over a day old, or the estimate passed 100 (the week must have reset): ask for a fresh one."""
    rs = sorted(((t, r) for r in readings or [] if (t := _epoch(r.get("at"))) is not None), key=lambda x: x[0])
    if not rs:
        return {"last": None, "estimate_pct": None, "learned": False, "old": True, "readings": 0}
    last_t, last = rs[-1]
    tok = pct = 0
    if ents is not None:
        for (ta, a), (tb, b) in zip(rs, rs[1:]):
            if b["pct"] > a["pct"] and tb - ta < WEEK_S:
                tok += tokens(ents, ta, tb)["total"]
                pct += b["pct"] - a["pct"]
    learned = tok > 0 and pct > 0
    est = last["pct"] + tokens(ents, last_t, now)["total"] / (tok / pct) if learned else last["pct"]
    return {"last": {"pct": last["pct"], "at": last["at"]}, "estimate_pct": est, "learned": learned,
            "old": now - last_t > MANUAL_OLD_S or est >= 100, "readings": len(rs)}


# ---------- GET /api/usage ----------

def _jobs(root: Path) -> list:
    out = []
    for e in folders.video_folders(root):
        if not e["has_job"]:
            continue
        try:
            job = js.load(Path(e["path"]))
        except (OSError, ValueError):
            continue
        if isinstance(job, dict):
            out.append((e, job))
    return out


def _window_of(job: dict, now: float) -> "tuple":
    start = _epoch(job.get("created")) or now
    done = ((job.get("steps") or {}).get("export") or {}).get("state") == "done"
    end = (_epoch(job.get("finished")) or _epoch(job.get("updated")) or now) if done else now
    return start, max(start, end), done


def _per_job(jobs: list, ents: list, now: float) -> list:
    wins = [(e, job, *_window_of(job, now)) for e, job in jobs]
    out = []
    for i, (e, job, start, end, done) in enumerate(wins):
        overlap = any(j != i and s < end and start < f for j, (_, _, s, f, _) in enumerate(wins))
        u = job.get("usage") if isinstance(job.get("usage"), dict) else {}
        a, b = u.get("start_pct"), u.get("finish_pct")
        t = tokens(ents, start, end)
        out.append({"name": e["name"], "practice": e["practice"], "done": done, "about": overlap,
                    "tokens": t["total"], "claude": t["claude"], "helpers": t["helpers"],
                    "pct": round(b - a, 1) if isinstance(a, (int, float)) and isinstance(b, (int, float)) and b >= a
                    else None})
    out.sort(key=lambda j: -j["tokens"])
    return out


def report(root: Path, gui: Path, now: "float | None" = None) -> dict:
    now = time.time() if now is None else now
    auto = read_auto(gui, now)
    stale = auto is None or auto["old"]
    logs = project_logs(root)
    ents = entries(logs) if logs else None
    jobs = _jobs(Path(root))
    per, counted = per_video_pct([job for e, job in jobs if not e["practice"]])
    man = manual(js.read_prefs(Path(gui) / "prefs.json").get("usage_readings") or [], ents, now) if stale else None
    if not stale:
        week, source = auto["week_pct"], "auto"
    elif man and man["estimate_pct"] is not None:
        week, source = man["estimate_pct"], "manual"
    else:
        week, source = None, None
    toks = None
    if ents is not None:
        midnight = datetime.fromtimestamp(now).astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = auto["week_resets_at"] - WEEK_S if auto and auto["week_resets_at"] else now - WEEK_S
        toks = {"today": tokens(ents, midnight.timestamp(), now + 1), "week": tokens(ents, week_start, now + 1),
                "per_job": _per_job(jobs, ents, now + 1)}
    return {"auto": auto, "stale": stale, "week_pct": week, "source": source, "per_video_pct": per,
            "videos_counted": counted, "videos_left": videos_left(week, per), "tokens": toks, "manual": man}
