"""edit-mo-to's project status line (spec "Usage read automatically"): Claude Code runs it inside {root}.

    .claude/edit-mo-to/run gui/statusline.py      (set in {root}/.claude/settings.json "statusLine")

Reads Claude Code's status JSON on stdin (https://code.claude.com/docs/en/statusline) and prints one short line:
`Week 41% · Now 23% · resets Fri 9 AM`, or, before the session's first reply or on a plan without limits, the model
and the context % (`Opus · context 12%`). It saves the plan windows that are present (rate_limits.seven_day and
rate_limits.five_hour: used_percentage 0-100 and resets_at in epoch seconds) with the time to {tmp}/gui/usage.json
(atomic write): {"at", "seven_day"?: {"used_percentage", "resets_at", "at"?}, "five_hour"?: {...}}. Numbers and times
only. With no window it writes nothing, so the last reading stays. A window this reply lacks keeps its last reading
while that window has not reset, with its own "at" (so a five-hour-only reply never wipes the week %, and the app still
sees how old the week reading is).

Fast and never fails the status line: standard library only, no network; any error still prints a line; exit 0.
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

WINDOWS = ("seven_day", "five_hour")
FALLBACK = "edit-mo-to"


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v


def _pct(v) -> int:
    return int(v + 0.5)   # half up, as the app rounds (Math.round)


def windows(data) -> dict:
    """The valid plan windows from the status JSON: {"seven_day"?: {"used_percentage", "resets_at"|None}, ...}."""
    rl = data.get("rate_limits") if isinstance(data, dict) else None
    out = {}
    if not isinstance(rl, dict):
        return out
    for name in WINDOWS:
        w = rl.get(name)
        if not isinstance(w, dict) or not _num(w.get("used_percentage")) or not 0 <= w["used_percentage"] <= 100:
            continue
        resets = w.get("resets_at")
        out[name] = {"used_percentage": w["used_percentage"], "resets_at": resets if _num(resets) else None}
    return out


def _when(epoch) -> str:
    dt = datetime.fromtimestamp(epoch).astimezone()
    hour = dt.hour % 12 or 12
    return f"{dt.strftime('%a')} {hour}{dt.strftime(':%M') if dt.minute else ''} {'AM' if dt.hour < 12 else 'PM'}"


def line(data) -> str:
    w = windows(data)
    parts = []
    if "seven_day" in w:
        parts.append(f"Week {_pct(w['seven_day']['used_percentage'])}%")
    if "five_hour" in w:
        parts.append(f"Now {_pct(w['five_hour']['used_percentage'])}%")
    if "seven_day" in w and w["seven_day"]["resets_at"] is not None:
        try:
            parts.append(f"resets {_when(w['seven_day']['resets_at'])}")
        except (OverflowError, OSError, ValueError):
            pass
    if parts:
        return " · ".join(parts)
    if not isinstance(data, dict):
        return FALLBACK
    model = data.get("model")
    name = model.get("display_name") if isinstance(model, dict) else None
    name = name.strip() if isinstance(name, str) and name.strip() else None
    ctx = data.get("context_window")
    used = ctx.get("used_percentage") if isinstance(ctx, dict) else None
    if name and _num(used):
        return f"{name} · context {_pct(used)}%"
    return name or FALLBACK


def _kept(old, name: str, now: float) -> "dict | None":
    """The last saved reading of a window this reply lacks, with its own time, while it has not reset; else None."""
    prev = old.get(name) if isinstance(old, dict) else None
    if not isinstance(prev, dict):
        return None
    pct, resets = prev.get("used_percentage"), prev.get("resets_at")
    at = prev.get("at") if isinstance(prev.get("at"), str) else old.get("at")
    if not (_num(pct) and 0 <= pct <= 100 and _num(resets) and resets > now and isinstance(at, str) and len(at) <= 40):
        return None
    return {"used_percentage": pct, "resets_at": resets, "at": at}


def save(data) -> None:
    w = windows(data)
    if not w:
        return
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import jobstate
    path = jobstate.gui_dir() / "usage.json"
    try:
        old = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = None
    for name in WINDOWS:
        if name not in w and (kept := _kept(old, name, time.time())):
            w[name] = kept
    jobstate.write_json_atomic(path, {"at": datetime.now().astimezone().isoformat(timespec="seconds"), **w})


def main() -> None:
    text = FALLBACK
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace") or "null")
        text = line(data)
        try:
            save(data)
        except Exception:  # noqa: BLE001 - a full disk or a bad path never blanks the status line
            pass
    except Exception:  # noqa: BLE001
        pass
    try:
        sys.stdout.buffer.write((text + "\n").encode("utf-8"))
        sys.stdout.flush()
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
