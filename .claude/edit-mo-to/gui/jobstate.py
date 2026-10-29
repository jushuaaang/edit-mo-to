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
import re
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
# It never changes a step's state; at the step's gate Claude turns it into a confirm question (steps.md, "Early inputs
# and their confirms"). append_event refuses an early input that is not in this table: everything else waits.
EARLY: dict[str, list[str]] = {
    "brief": ["link", "paste", "instructions", "upload"],  # everything on the page, any time (upload: reference files)
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


def _check_early(event: dict) -> None:
    """An early input is an `answer` or `upload` with target "<step>:<id>" from EARLY (and step = that step)."""
    target = event.get("target")
    step, _, qid = target.partition(":") if isinstance(target, str) else ("", "", "")
    if event.get("type") not in ("answer", "upload") or qid not in EARLY.get(step, []) \
            or event.get("step", step) != step:
        raise ValueError(f"this can't be saved early ({target!r}); it waits until Claude reaches its step")


def append_event(folder: Path, event: dict) -> dict:
    if event.get("type") not in EVENT_TYPES:
        raise ValueError(f"event type must be one of {EVENT_TYPES}, got {event.get('type')!r}")
    if "early" in event:
        if not isinstance(event["early"], bool):
            raise ValueError("early must be true or false")
        if event["early"] and event.get("gate"):
            raise ValueError("an early input answers no gate (gate must be null)")
        if event["early"]:
            _check_early(event)
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

PREFS = {"notify": True, "sound": True, "ui_lang": "auto", "ui_lang_detected": "en",   # known keys and defaults
         "avoid_models": [], "default_model": None,   # the models Claude never picks / picks first ("<site>:<model>")
         # Generate for me (only shown where account.generate_allowed): when the editor accepted the Flow warning (ISO
         # time; asked once), and the ElevenLabs voice id and model id elevenlabs_vo.py uses
         "generate_warned_at": None, "elevenlabs_voice": None, "elevenlabs_model": None,
         # the weekly % the editor typed from Claude's /usage (the dashboard's manual fallback), oldest first:
         # [{"pct": 0-100, "at": ISO time}], the last USAGE_READINGS_KEEP kept (add_usage_reading)
         "usage_readings": []}
USAGE_READINGS_KEEP = 20
PREF_CHOICES = {"ui_lang": ("auto", "en", "tl"), "ui_lang_detected": ("en", "tl")}   # string prefs: allowed values
MODEL_PREFS = ("avoid_models", "default_model")   # checked against generators.json's model ids
ID_PREFS = {"elevenlabs_voice": re.compile(r"[A-Za-z0-9]{1,64}"), "elevenlabs_model": re.compile(r"[a-z0-9_]{1,64}")}


def _model_ids() -> set:
    tools = str(Path(__file__).resolve().parents[1] / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import generators
    return set(generators.model_ids())


def check_pref(key: str, value) -> None:
    """ValueError unless key is known and value has its type (and, for a string pref, is one of its choices; for a
    model pref, generators.json's "<site>:<model>" ids)."""
    if key not in PREFS:
        raise ValueError(f"unknown setting: {key}")
    if key == "avoid_models":
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value) or len(set(value)) != len(value):
            raise ValueError("avoid_models must be a list of different model ids")
        unknown = [x for x in value if x not in _model_ids()]
        if unknown:
            raise ValueError(f"unknown model: {', '.join(unknown)}")
    elif key == "default_model":
        if value is not None and (not isinstance(value, str) or value not in _model_ids()):
            raise ValueError(f"unknown model: {value}")
    elif key == "generate_warned_at":
        try:
            ok = isinstance(value, str) and len(value) <= 40 and datetime.fromisoformat(value) is not None
        except ValueError:
            ok = False
        if value is not None and not ok:
            raise ValueError("generate_warned_at must be a time (ISO) or null")
    elif key == "usage_readings":
        if not isinstance(value, list) or len(value) > USAGE_READINGS_KEEP:
            raise ValueError(f"usage_readings must be a list of at most {USAGE_READINGS_KEEP} readings")
        for r in value:
            pct = r.get("pct") if isinstance(r, dict) else None
            if not isinstance(pct, (int, float)) or isinstance(pct, bool) or not 0 <= pct <= 100:
                raise ValueError("a usage reading needs pct, a number from 0 to 100")
            try:
                ok = isinstance(r.get("at"), str) and len(r["at"]) <= 40 and datetime.fromisoformat(r["at"]) is not None
            except ValueError:
                ok = False
            if not ok or set(r) != {"pct", "at"}:
                raise ValueError("a usage reading is {\"pct\", \"at\"} with at an ISO time")
    elif key in ID_PREFS:
        if value is not None and (not isinstance(value, str) or not ID_PREFS[key].fullmatch(value)):
            raise ValueError(f"{key} must be an id (letters, digits{', _' if key == 'elevenlabs_model' else ''}) or null")
    elif key in PREF_CHOICES:
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


def _clean(saved: dict) -> dict:
    """Saved prefs with only known, valid keys; an avoid list keeps its known ids; an avoided default is dropped."""
    out = {}
    for k, v in saved.items():
        if k == "avoid_models" and isinstance(v, list):
            ids = _model_ids()
            v = list(dict.fromkeys(x for x in v if isinstance(x, str) and x in ids))
        if k in PREFS and _valid(k, v):
            out[k] = v
    if out.get("default_model") in out.get("avoid_models", []):
        del out["default_model"]
    return out


def read_prefs(path: Path) -> dict:
    """Every known pref: the saved value when it is valid, else the default (a missing or broken file = defaults)."""
    try:
        saved = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    saved = _clean(saved if isinstance(saved, dict) else {})
    return {k: saved[k] if k in saved else (list(v) if isinstance(v, list) else v) for k, v in PREFS.items()}


class PrefsDamaged(ValueError):
    """prefs.json exists but can't be read or makes no sense: a save must not overwrite it (that would wipe the
    editor's avoid list, and the next pick could choose a model they avoid). `why` is the plain reason."""

    def __init__(self, message: str, why: str = ""):
        super().__init__(message)
        self.why = why


def _saved_prefs(path: Path) -> dict:
    """The saved prefs to merge a change into: {} when there is no file yet. A file that can't be read, isn't a JSON
    object, or holds a wrong type for the model settings (the same checks as generators.read_prefs, which makes pick
    refuse) raises PrefsDamaged, and the file is left as it is."""
    def damaged(why: str):
        return PrefsDamaged(f"Your settings file is damaged ({why}), so nothing was saved. This keeps your \"never use\" "
                            f"models safe. Fix or delete {Path(path).as_posix()}, then set your settings again.", why)
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as e:
        raise damaged(f"can't read it: {e.strerror or e}") from None
    try:
        saved = json.loads(raw)
    except ValueError:
        raise damaged("not valid JSON") from None
    if not isinstance(saved, dict):
        raise damaged("not a settings object")
    avoid, default = saved.get("avoid_models", []), saved.get("default_model")
    if not isinstance(avoid, list) or not all(isinstance(x, str) for x in avoid):
        raise damaged("the never-use list is not a list of models")
    if default is not None and not isinstance(default, str):
        raise damaged("Claude's default model is not a model")
    return saved


def prefs_damaged(path: Path) -> "str | None":
    """The plain reason a save into prefs.json would refuse (PrefsDamaged), or None when it would not."""
    try:
        _saved_prefs(path)
    except PrefsDamaged as e:
        return e.why
    return None


@contextmanager
def prefs_lock(gui: Path):
    """The cross-process lock for <gui>/prefs.json (<gui>/prefs.lock), shared by the server and job.py."""
    with _file_lock(Path(gui) / "prefs.lock"):
        yield


def update_prefs(gui: Path, patch: dict) -> dict:
    """Check every key of patch, then merge it into <gui>/prefs.json under prefs_lock; the file keeps only known,
    valid keys that were saved (defaults are not written). Claude's default model can't be one it avoids (ValueError;
    send both keys to change both). A damaged prefs.json is never overwritten (PrefsDamaged, a ValueError).
    Returns read_prefs."""
    if not isinstance(patch, dict) or not patch:
        raise ValueError("nothing to save")
    for key, value in patch.items():
        check_pref(key, value)
    path = Path(gui) / "prefs.json"
    with prefs_lock(gui):
        merged = {**_clean(_saved_prefs(path)), **patch}
        if merged.get("default_model") and merged["default_model"] in merged.get("avoid_models", []):
            raise ValueError("Claude's default model can't be a model Claude avoids")
        write_json_atomic(path, merged)
    return read_prefs(path)


def add_usage_reading(gui: Path, pct) -> dict:
    """Append the weekly % the editor typed (0-100) with the time to prefs usage_readings, under prefs_lock (the last
    USAGE_READINGS_KEEP stay). A damaged prefs.json is never overwritten (PrefsDamaged). Returns read_prefs."""
    if not isinstance(pct, (int, float)) or isinstance(pct, bool) or not 0 <= pct <= 100:
        raise ValueError("type the weekly % as a number from 0 to 100")
    path = Path(gui) / "prefs.json"
    with prefs_lock(gui):
        merged = _clean(_saved_prefs(path))
        readings = (merged.get("usage_readings") or []) + [{"pct": pct, "at": _now()}]
        merged["usage_readings"] = readings[-USAGE_READINGS_KEEP:]
        write_json_atomic(path, merged)
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
