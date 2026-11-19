"""Bug reports and suggestions from the Settings page, kept on this computer.

    save(entry, root) -> dict      append {"type","title","text","step"?,"at"} to {root}/.claude/edit-mo-to/feedback.jsonl
    items(root) -> list            every saved entry, oldest first
    issue_url(entry, version, os_name) -> str
                                   a pre-filled new-issue link; carries only what the editor typed, plus the
                                   edit-mo-to version, the OS and the step picked (never paths or job data)
    version(root) -> str           git short commit of {root}, or "unknown"
    os_name() -> str               "Windows", "macOS" or platform.system()

Standard library only. Nothing is sent anywhere: the editor opens the link and submits it themselves.
"""
import json
import platform
import subprocess
import sys
import threading
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jobstate as js  # noqa: E402

REPO = "https://github.com/jushuaaang/edit-mo-to"
LABELS = {"bug": "bug", "suggestion": "enhancement"}
MAX_TITLE, MAX_TEXT = 200, 20000
_lock = threading.Lock()


def _path(root: Path) -> Path:
    return Path(root) / ".claude" / "edit-mo-to" / "feedback.jsonl"


def _text(entry: dict, field: str, limit: int) -> str:
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"feedback needs a {field}")
    if len(value) > limit:
        raise ValueError(f"feedback {field} is longer than {limit} characters")
    return value.strip()


def clean(entry: dict) -> dict:
    """Keep only the fields the editor typed; ValueError on anything malformed."""
    if not isinstance(entry, dict):
        raise ValueError("feedback must be an object")
    if entry.get("type") not in LABELS:
        raise ValueError(f"feedback type must be one of {', '.join(LABELS)}")
    out = {"type": entry["type"], "title": _text(entry, "title", MAX_TITLE), "text": _text(entry, "text", MAX_TEXT)}
    step = entry.get("step")
    if step:
        if step not in js.STEPS:
            raise ValueError(f"unknown step: {step!r}")
        out["step"] = step
    return out


def save(entry: dict, root: Path) -> dict:
    out = clean(entry)
    out["at"] = js._now()
    path = _path(root)
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(out, ensure_ascii=False) + "\n")
    return out


def items(root: Path) -> list:
    path = _path(root)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").split("\n"):
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue  # a torn or hand-edited line never hides the rest
    return out


def version(root: Path) -> str:
    try:
        r = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else "unknown"


def os_name() -> str:
    if sys.platform == "win32":
        return "Windows"
    if sys.platform == "darwin":
        return "macOS"
    return platform.system()


def issue_url(entry: dict, version: str, os_name: str) -> str:
    facts = []
    if entry.get("step"):
        facts.append(f"Step: {entry['step']}")
    facts += [f"edit-mo-to version: {version}", f"OS: {os_name}"]
    body = entry["text"] + "\n\n" + "\n".join(facts)
    query = urllib.parse.urlencode({"title": entry["title"], "body": body, "labels": LABELS[entry["type"]]})
    return f"{REPO}/issues/new?{query}"
