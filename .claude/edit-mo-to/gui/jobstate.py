"""Shared job state for the edit-mo-to companion GUI.

One video folder keeps its state in `<folder>/.edit-mo-to/`:
  job.json        step states, the open gate, outputs, log (written by job.py / server create; atomic)
  inbox.jsonl     editor events, one JSON line each (written only by the server; seq numbers)
  listening.json  {"pid","since","step"} while Claude is blocked in wait.py for an answer

job.py, wait.py and server.py all build on this module. Standard library only; no machine paths.
"""
import json
import os
import sys
import threading
from datetime import datetime
from pathlib import Path

STEPS = ["brief", "script", "storyboard", "voiceover", "timing", "prompts", "clips",
         "build", "review", "captions", "music", "export"]
STATES = ("pending", "working", "waiting", "done", "skipped", "error")
GATE_KINDS = ("choice", "multi", "text", "confirm", "file")
EVENT_TYPES = ("answer", "approve", "edit", "comment", "message", "action", "upload")

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _lock(folder: Path) -> threading.Lock:
    key = str(Path(folder).resolve())
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


def state_dir(folder: Path) -> Path:
    return Path(folder) / ".edit-mo-to"


def _job_path(folder: Path) -> Path:
    return state_dir(folder) / "job.json"


def _inbox_path(folder: Path) -> Path:
    return state_dir(folder) / "inbox.jsonl"


def new_job(folder: Path, client: str, product: str) -> dict:
    now = _now()
    posix = Path(folder).as_posix()
    return {"version": 1, "folder": posix, "created": now, "updated": now,
            "card": {"client": client, "product": product, "folder": posix},
            "steps": {s: {"state": "pending", "note": ""} for s in STEPS},
            "gate": None, "outputs": {}, "log": [], "handled": []}


def validate(job: dict) -> None:
    for name, step in (job.get("steps") or {}).items():
        if name not in STEPS:
            raise ValueError(f"unknown step: {name}")
        if step.get("state") not in STATES:
            raise ValueError(f"unknown state for step {name}: {step.get('state')!r}")
    gate = job.get("gate")
    if gate is not None:
        for field in ("id", "text", "kind"):
            if not gate.get(field):
                raise ValueError(f"gate is missing {field}")
        if gate["kind"] not in GATE_KINDS:
            raise ValueError(f"gate kind must be one of {GATE_KINDS}, got {gate['kind']!r}")


def load(folder: Path) -> dict:
    return json.loads(_job_path(folder).read_text(encoding="utf-8"))


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def save(folder: Path, job: dict) -> None:
    validate(job)
    job["updated"] = _now()
    _write_atomic(_job_path(folder), json.dumps(job, ensure_ascii=False, indent=2))


def read_events(folder: Path, after: int = 0) -> list[dict]:
    path = _inbox_path(folder)
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            ev = json.loads(line)
            if ev.get("seq", 0) > after:
                events.append(ev)
    return events


def append_event(folder: Path, event: dict) -> dict:
    with _lock(folder):
        last = read_events(folder)
        ev = dict(event)
        ev["seq"] = (last[-1]["seq"] if last else 0) + 1
        ev["at"] = _now()
        gate = ev.get("gate")
        if gate:
            try:
                open_gate = (load(folder).get("gate") or {}).get("id")
            except FileNotFoundError:
                open_gate = None
            if gate != open_gate:
                ev["stale"] = True
        path = _inbox_path(folder)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        return ev


def unhandled(folder: Path) -> list[dict]:
    handled = set(load(folder).get("handled", []))
    return [e for e in read_events(folder) if e["seq"] not in handled]


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == 259  # STILL_ACTIVE
        finally:
            k32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _listening_path(folder: Path) -> Path:
    return state_dir(folder) / "listening.json"


def write_listening(folder: Path, step: str | None) -> Path:
    path = _listening_path(folder)
    _write_atomic(path, json.dumps({"pid": os.getpid(), "since": _now(), "step": step}, ensure_ascii=False))
    return path


def clear_listening(folder: Path) -> None:
    _listening_path(folder).unlink(missing_ok=True)


def listening(folder: Path) -> dict | None:
    try:
        data = json.loads(_listening_path(folder).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None
    return data if pid_alive(int(data.get("pid", 0))) else None
