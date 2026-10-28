"""Shared job state for the edit-mo-to companion GUI.

One video folder keeps its state in `<folder>/.edit-mo-to/`:
  job.json        step states, the open gate, outputs, log (written by job.py / server create; atomic)
  inbox.jsonl     editor events, one JSON line each (written only by the server; seq numbers)
  job.lock        the folder lock (an OS file lock): every load-modify-save of job.json and every inbox
                  append runs under lock(folder), across threads and processes (Claude runs job.py calls
                  in parallel, and a second GUI server must never interleave inbox appends)
  listening.json  {"pid","since","beat","step"} while Claude is blocked in wait.py for an answer.
                  wait.py calls write_listening on every poll as a heartbeat (fresh "beat" epoch
                  seconds); listening() only trusts the file while the pid is alive AND the beat
                  is newer than max_age, so a reused pid cannot look like a live waiter.

job.py, wait.py and server.py all build on this module. Standard library only; no machine paths.
"""
import errno
import json
import os
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

STEPS = ["brief", "script", "storyboard", "voiceover", "timing", "prompts", "clips",
         "build", "review", "captions", "music", "export"]
STATES = ("pending", "working", "waiting", "done", "skipped", "error")
GATE_KINDS = ("choice", "multi", "text", "confirm", "file")
EVENT_TYPES = ("answer", "approve", "edit", "comment", "message", "action", "upload")
# Working ahead (spec "Working ahead"): step -> the inputs the editor may give before Claude reaches the step.
# An early input is an `answer` (target "<step>:<id>") or `upload` event with "early": true and "gate": null.
# It never changes a step's state; at the step's gate Claude turns it into a confirm question.
EARLY: dict[str, list[str]] = {
    "brief": ["link", "paste", "instructions", "refs"],  # everything on the page, any time
    "script": ["own_script"],
    "voiceover": ["upload"],
    "prompts": ["broll_source", "generator", "generator_model"],
    "clips": ["clips_folder"],
    "captions": ["who"],
    "music": ["source", "upload"],
}

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
LOCK_WAIT = 30.0  # seconds a writer waits for the folder lock before failing loudly


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _lock(path: Path) -> threading.Lock:
    key = str(Path(path).resolve())
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


def _try_os_lock(f) -> bool:
    """Take an exclusive OS lock on the open lock file without blocking; False when another holder has it."""
    try:
        if sys.platform == "win32":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError as e:
        if e.errno in (errno.ENOTSUP, errno.EOPNOTSUPP, errno.ENOLCK):
            return True  # a file system without locks (rare): the in-process lock still holds
        return False


def _os_unlock(f) -> None:
    try:
        if sys.platform == "win32":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass  # closing the file releases it anyway


@contextmanager
def _file_lock(path: Path):
    """A thread lock first (one waiter per process), then an OS lock (fcntl.flock / msvcrt.locking) on `path`.
    The OS releases it when the holder exits or crashes, so there is no stale lock to clean up. Not re-entrant."""
    path = Path(path)
    with _lock(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a+b") as f:
            deadline = time.monotonic() + LOCK_WAIT
            while not _try_os_lock(f):
                if time.monotonic() > deadline:
                    raise TimeoutError(f"{path} is held by another process for over {LOCK_WAIT:.0f} s")
                time.sleep(0.01)
            try:
                yield
            finally:
                _os_unlock(f)


@contextmanager
def lock(folder: Path):
    """The per-folder writer lock, across threads and processes: `with jobstate.lock(folder): ...`, on
    <folder>/.edit-mo-to/job.lock (see _file_lock). Not re-entrant: never nest it."""
    with _file_lock(state_dir(folder) / "job.lock"):
        yield


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
        if not isinstance(step, dict):
            raise ValueError(f"step {name} must be an object")
        if step.get("state") not in STATES:
            raise ValueError(f"unknown state for step {name}: {step.get('state')!r}")
    gate = job.get("gate")
    if gate is not None:
        if not isinstance(gate, dict):
            raise ValueError("gate must be an object")
        for field in ("id", "title"):
            if not isinstance(gate.get(field), str) or not gate[field]:
                raise ValueError(f"gate is missing {field}")
        questions = gate.get("questions")
        if not isinstance(questions, list) or not questions:
            raise ValueError("gate needs a non-empty questions list")
        for i, q in enumerate(questions, 1):
            if not isinstance(q, dict):
                raise ValueError(f"gate question {i} must be an object")
            for field in ("id", "text", "kind"):
                if not q.get(field):
                    raise ValueError(f"gate question {i} is missing {field}")
            if q["kind"] not in GATE_KINDS:
                raise ValueError(f"gate question {q['id']}: kind must be one of {GATE_KINDS}, got {q['kind']!r}")


def _retry(fn):
    """Run fn, retrying PermissionError (Windows: file briefly open elsewhere) ~10 times."""
    for attempt in range(10):
        try:
            return fn()
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.025)


def load(folder: Path) -> dict:
    return json.loads(_retry(lambda: _job_path(folder).read_text(encoding="utf-8")))


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        _retry(lambda: os.replace(tmp, path))
    finally:
        tmp.unlink(missing_ok=True)


def write_json_atomic(path: Path, data) -> None:
    """Write data as UTF-8 JSON to path atomically (temp file + os.replace)."""
    _write_atomic(Path(path), json.dumps(data, ensure_ascii=False, indent=1) + "\n")


def save(folder: Path, job: dict) -> None:
    validate(job)
    job["updated"] = _now()
    _write_atomic(_job_path(folder), json.dumps(job, ensure_ascii=False, indent=2))


def read_events(folder: Path, after: int = 0) -> list[dict]:
    path = _inbox_path(folder)
    if not path.exists():
        return []
    # split on "\n" only: str.splitlines() also splits on U+2028/U+2029/U+0085, which
    # json.dumps(ensure_ascii=False) leaves unescaped inside strings
    text = _retry(lambda: path.read_text(encoding="utf-8"))
    lines = [ln for ln in text.split("\n") if ln.strip()]
    events = []
    for i, line in enumerate(lines):
        try:
            ev = json.loads(line)
        except ValueError:
            if i == len(lines) - 1:
                break  # torn final line (crash or half-written append): ignore it
            raise
        if ev.get("seq", 0) > after:
            events.append(ev)
    return events


def append_event(folder: Path, event: dict) -> dict:
    if event.get("type") not in EVENT_TYPES:
        raise ValueError(f"event type must be one of {EVENT_TYPES}, got {event.get('type')!r}")
    if "early" in event:
        if not isinstance(event["early"], bool):
            raise ValueError("early must be true or false")
        if event["early"] and event.get("gate"):
            raise ValueError("an early input answers no gate (gate must be null)")
    with lock(folder):
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
        data = (json.dumps(ev, ensure_ascii=False) + "\n").encode("utf-8")
        with path.open("ab+") as f:
            raw = f.read() if f.seek(0) == 0 else b""
            if raw and not raw.endswith(b"\n"):
                # torn tail from a crash mid-append (we are the single writer, so never a live
                # write): cut it back to the last complete line so it cannot glue onto our event
                f.truncate(raw.rfind(b"\n") + 1)
            f.seek(0, os.SEEK_END)
            f.write(data)
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


def gui_dir() -> Path:
    """<tmp>/gui; tmp from machine.PATHS at call time (EDIT_MO_TO_GUI_TMP overrides, for tests)."""
    tmp = os.environ.get("EDIT_MO_TO_GUI_TMP")
    if not tmp:
        tools = str(Path(__file__).resolve().parents[1] / "tools")
        if tools not in sys.path:
            sys.path.insert(0, tools)
        import machine
        tmp = machine.PATHS["tmp"]
    return Path(tmp) / "gui"


def _current_path() -> Path:
    return gui_dir() / "current.json"


# ---------- this computer's GUI prefs: <tmp>/gui/prefs.json (the server's Settings and `job.py lang`) ----------

PREFS = {"notify": True, "sound": True, "ui_lang": "auto", "ui_lang_detected": "en"}  # known keys and defaults
PREF_CHOICES = {"ui_lang": ("auto", "en", "tl"), "ui_lang_detected": ("en", "tl")}   # string prefs: allowed values


def check_pref(key: str, value) -> None:
    """ValueError unless key is known and value has its type (and, for a string pref, is one of its choices)."""
    if key not in PREFS:
        raise ValueError(f"unknown setting: {key}")
    if key in PREF_CHOICES:
        if not isinstance(value, str) or value not in PREF_CHOICES[key]:
            raise ValueError(f"{key} must be one of {', '.join(PREF_CHOICES[key])}")
    elif not isinstance(value, bool):  # every other pref is a switch
        raise ValueError(f"{key} must be true or false")


def _valid(key: str, value) -> bool:
    try:
        check_pref(key, value)
        return True
    except ValueError:
        return False


def read_prefs(path: Path) -> dict:
    """Every known pref: the saved value when it is valid, else the default (a missing or broken file = defaults)."""
    try:
        saved = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    saved = saved if isinstance(saved, dict) else {}
    return {k: saved[k] if k in saved and _valid(k, saved[k]) else v for k, v in PREFS.items()}


@contextmanager
def prefs_lock(gui: Path):
    """The cross-process lock for <gui>/prefs.json (<gui>/prefs.lock), shared by the server and job.py."""
    with _file_lock(Path(gui) / "prefs.lock"):
        yield


def update_prefs(gui: Path, patch: dict) -> dict:
    """Check every key of patch, then merge it into <gui>/prefs.json under prefs_lock; the file keeps only known,
    valid keys that were saved (defaults are not written). Returns read_prefs."""
    if not isinstance(patch, dict) or not patch:
        raise ValueError("nothing to save")
    for key, value in patch.items():
        check_pref(key, value)
    path = Path(gui) / "prefs.json"
    with prefs_lock(gui):
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            saved = {}
        saved = {k: v for k, v in (saved if isinstance(saved, dict) else {}).items() if k in PREFS and _valid(k, v)}
        write_json_atomic(path, {**saved, **patch})
    return read_prefs(path)


def set_current(folder: Path) -> None:
    _write_atomic(_current_path(), json.dumps({"folder": Path(folder).as_posix()}, ensure_ascii=False))


def get_current() -> str | None:
    try:
        folder = json.loads(_retry(lambda: _current_path().read_text(encoding="utf-8"))).get("folder")
    except (OSError, ValueError, AttributeError):
        return None
    return folder or None


def _listening_path(folder: Path) -> Path:
    return state_dir(folder) / "listening.json"


def write_listening(folder: Path, step: str | None) -> Path:
    """Write (or refresh) listening.json; call it on every poll as the heartbeat."""
    path = _listening_path(folder)
    pid, since = os.getpid(), _now()
    try:
        old = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(old, dict) and old.get("pid") == pid and old.get("since"):
            since = old["since"]
    except (OSError, ValueError):
        pass
    _write_atomic(path, json.dumps({"pid": pid, "since": since, "beat": time.time(), "step": step},
                                   ensure_ascii=False))
    return path


def clear_listening(folder: Path) -> None:
    _listening_path(folder).unlink(missing_ok=True)


def listening(folder: Path, max_age: float = 10.0) -> dict | None:
    try:
        data = json.loads(_retry(lambda: _listening_path(folder).read_text(encoding="utf-8")))
        pid, beat = int(data["pid"]), float(data["beat"])
    except (OSError, ValueError, TypeError, KeyError):
        return None
    if time.time() - beat > max_age:
        return None
    return data if pid_alive(pid) else None
