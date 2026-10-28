"""Local API server for the edit-mo-to companion GUI (standard library only).

Binds to 127.0.0.1. Reads job state, appends the editor's answers to the inbox, keeps gui.json, accepts
uploads into the video folder and runs only read-only checks. It never writes a CapCut project and never
runs a workflow tool that changes files: those buttons become inbox events that Claude acts on.

    python server.py [--port N] [--root R] [--tmp D]   default: gui_port from machine.json, else 4810 (next free one
                                     if taken); root and tmp from machine.json. Prints {"ok": true, "url": ...};
                                     writes {tmp}/gui/server.json

GET /api/ping (no token) answers {"app", "version", "pid", "config"}: `version` is a hash of the GUI code (gui/*.py and
static/**, read at import), `config` a hash of the root and tmp this server runs with. launch.py replaces our server
when either differs from what it would start now (an update was pulled, or Settings changed a path).

Security: every route except GET /api/ping and static files needs the per-launch token (cookie `emt`, set
by GET /?k=<token>, or header X-EMT-Token). A Host other than 127.0.0.1:<port> / localhost:<port>, or a
foreign Origin, is refused (403). Files are read or written only inside {root} and {tmp}; writes (inbox,
gui.json, uploads, new job) only inside a video folder of {root} (folders.is_video_folder). One exception,
read-only: GET /api/temp-en may also read a CapCut project under {capcut_drafts}. GET/POST /api/prefs keep this computer's
GUI prefs (jobstate.PREFS: known keys only) in {tmp}/gui/prefs.json.

POST /api/practice is the one route that starts a program (spec "Try a practice video"): on the editor's click it opens
a visible Terminal (macOS) or command window (Windows) in {root} running `claude /practice-muna`, so the editor's own
Claude starts the practice run. The command and the folder are fixed here (practice_argv); nothing in the request is
read. At most one launch per PRACTICE_GAP seconds, and none while one is still starting.
"""
import argparse
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

GUI = Path(__file__).resolve().parent
for _p in (GUI, GUI.parent / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import checks  # noqa: E402
import feedback  # noqa: E402
import folders  # noqa: E402
import generators  # noqa: E402
import jobstate as js  # noqa: E402
import machine  # noqa: E402

APP, DEFAULT_PORT = "edit-mo-to-gui", 4810
STATIC = GUI / "static"


def code_version(gui: Path = GUI) -> str:
    """A short hash of the GUI code: every gui/*.py and every file under gui/static/, by relative path and bytes."""
    digest = hashlib.sha1()
    files = sorted(gui.glob("*.py")) + sorted(p for p in (gui / "static").rglob("*") if p.is_file())
    for p in files:
        digest.update(p.relative_to(gui).as_posix().encode("utf-8") + b"\0")
        digest.update(p.read_bytes() + b"\0")
    return digest.hexdigest()[:12]


def fingerprint(root: Path, tmp: Path) -> str:
    """A short hash of the paths a server runs with; ping shows it instead of the paths themselves."""
    return hashlib.sha1(f"{Path(root).as_posix()}\n{Path(tmp).as_posix()}".encode("utf-8")).hexdigest()[:12]


API_VERSION = code_version()
MIB = 1 << 20
CHUNK, MAX_JSON, BIG = MIB, MIB, 4 << 30
MEDIA = {"mp3", "wav", "m4a", "aac"}
UPLOADS = {  # kind: (subfolder, step for the event, allowed extensions, size limit)
    "refs": ("refs", "brief", {"pdf", "docx", "doc", "txt", "md", "png", "jpg", "jpeg", "webp", "gif",
                               "mp4", "mov", "m4v", "mp3", "wav", "m4a"}, BIG),
    "keyframe": ("storyboard", "storyboard", {"png", "jpg", "jpeg", "webp"}, 50 * MIB),
    "vo": ("vo", "voiceover", MEDIA, BIG),
    "music": ("music", "music", MEDIA, BIG),
}
KEYFRAME_ID = re.compile(r"(SB|CHAR)-\d+")
KEYFRAME_EXTS = UPLOADS["keyframe"][2]
PENDING_TYPES = {"edit", "approve", "action"}
RECENT_EVENTS = 200
SETTINGS_KEYS = ("root", "python", "tmp", "mcp_servers", "capcut_drafts", "gui_port")
SETTINGS_DIRS = {"root": True, "python": False, "tmp": True, "mcp_servers": True, "capcut_drafts": True}
PYTHON_NAMES = {"python", "python3", "python.exe", "python3.exe"}
RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(10)), *(f"lpt{i}" for i in range(10))}
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
         ".txt": "text/plain; charset=utf-8", ".md": "text/markdown; charset=utf-8",
         ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
         ".webp": "image/webp", ".gif": "image/gif", ".woff2": "font/woff2", ".pdf": "application/pdf",
         ".mp4": "video/mp4", ".mov": "video/quicktime", ".m4v": "video/x-m4v", ".mp3": "audio/mpeg",
         ".wav": "audio/wav", ".m4a": "audio/mp4", ".aac": "audio/aac"}
_upload_lock = threading.Lock()
_prefs_lock = threading.Lock()


class HttpError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def _content_type(path: Path) -> str:
    return TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _stamp(path: Path) -> str:
    try:
        st = path.stat()
        return f"{path.name}:{st.st_mtime_ns}:{st.st_size}"
    except OSError:
        return f"{path.name}:-"


def _need_str(body: dict, key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        raise HttpError(400, f"{key} is required")
    return value.strip()


# ---------- job helpers ----------

def _keyframes(folder: Path) -> "tuple[dict, dict]":
    """({id: resolved path}, {id: mtime_ns}) of storyboard/SB-n and CHAR-n images. The mtime is the page's image
    cache-buster, so a keyframe replaced from outside the app (same name) shows the new picture."""
    try:
        entries = sorted((folder / "storyboard").iterdir())
    except OSError:
        return {}, {}
    out, mtimes = {}, {}
    for p in entries:
        if KEYFRAME_ID.fullmatch(p.stem) and p.suffix[1:].lower() in KEYFRAME_EXTS and p.stem not in out:
            try:
                st = p.stat()
            except OSError:
                continue
            if p.is_file():
                out[p.stem], mtimes[p.stem] = p.resolve().as_posix(), st.st_mtime_ns
    return out, mtimes


def _voice_files(folder: Path) -> list:
    """Audio files in vo/ (resolved, by name), however they got there: the "what to do now" strip asks for a
    voiceover only when there is none. Hidden files (a running upload's .part) are skipped."""
    try:
        entries = sorted((folder / "vo").iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return []
    return [p.resolve().as_posix() for p in entries
            if not p.name.startswith(".") and p.suffix[1:].lower() in MEDIA and p.is_file()]


def _output_paths(folder: Path, job: dict, roots: list) -> dict:
    """{step: {kind: resolved path inside roots, or None}}; a path outside roots is never touched."""
    out = {}
    for step, kinds in (job.get("outputs") or {}).items():
        for kind, ref in (kinds or {}).items():
            path = Path(ref["path"]) if isinstance(ref, dict) and isinstance(ref.get("path"), str) else None
            try:
                path = None if path is None else folders.safe_path(path if path.is_absolute() else folder / path,
                                                                   roots)
            except PermissionError:
                path = None
            out.setdefault(step, {})[kind] = path
    return out


def _listening_key(listening: "dict | None") -> str:
    """The listening state without the heartbeat, so a waiting Claude does not change the ETag every poll."""
    if not listening:
        return "not-listening"
    return json.dumps({k: listening.get(k) for k in ("pid", "step", "since")}, sort_keys=True)


def _summary(entry: dict) -> dict:
    out = {**entry, "client": None, "product": None, "style": None, "language": None,
           "step": None, "waiting": False, "progress": 0.0}
    if not entry["has_job"]:
        return out
    try:
        job = js.load(Path(entry["path"]))
    except (OSError, ValueError):
        return {**out, "error": "job.json could not be read"}
    card, steps = job.get("card") or {}, job.get("steps") or {}
    state = {s: (steps.get(s) or {}).get("state", "pending") for s in js.STEPS}
    active = [s for s in js.STEPS if state[s] in ("working", "waiting", "error")]
    pending = [s for s in js.STEPS if state[s] == "pending"]
    out.update({k: card.get(k) for k in ("client", "product", "style", "language")})
    out["step"] = (active or pending or [None])[0]
    out["waiting"] = bool(job.get("gate"))
    out["progress"] = sum(state[s] in ("done", "skipped") for s in js.STEPS) / len(js.STEPS)
    return out


# ---------- routes: each takes (handler, query) and returns a JSON-able object, or None if it replied ----------

def r_ping(h, q):
    return {"app": APP, "version": API_VERSION, "pid": os.getpid(), "config": fingerprint(h.server.root, h.server.tmp)}


def r_jobs(h, q):
    return [_summary(e) for e in folders.video_folders(h.server.root)]


def r_current(h, q):
    return {"folder": js.get_current()}


def _generators() -> "dict | None":
    """generators.json for the prompts page's site and model choices (the page keeps no list of its own)."""
    try:
        return {**generators.load(), "safe": generators.strictest()}  # safe: the limits used for an unknown model
    except (OSError, ValueError):
        return None


def r_job(h, q):
    folder = h.job_folder(q.get("folder"))
    job = js.load(folder)
    sd, sb = js.state_dir(folder), folder / "storyboard"
    (keyframes, keyframe_mtimes), listening = _keyframes(folder), js.listening(folder)
    vo = _voice_files(folder)
    outputs = _output_paths(folder, job, [h.server.root, h.server.tmp])
    parts = [folder.as_posix(), *(_stamp(p) for p in (sd / "job.json", sd / "inbox.jsonl", sd / "gui.json",
                                                      sb, sb / "storyboard.json")),
             *(_stamp(Path(p)) for p in keyframes.values()), _stamp(folder / "vo"), *(_stamp(Path(p)) for p in vo),
             *(_stamp(p) for kinds in outputs.values() for p in kinds.values() if p is not None),
             _stamp(generators.FILE), _listening_key(listening)]
    etag = '"' + hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:20] + '"'
    if h.headers.get("If-None-Match") == etag:
        h.reply(304, b"", None, {"ETag": etag})
        return None
    body = {"job": job, "listening": listening,
            "pending": [e for e in js.unhandled(folder) if e.get("type") in PENDING_TYPES],
            "events": js.read_events(folder)[-RECENT_EVENTS:],  # step messages, answers already sent
            "keyframes": keyframes, "keyframe_mtimes": keyframe_mtimes, "vo": vo,
            "storyboard": _read_json(sb / "storyboard.json"),
            "gui": _read_json(sd / "gui.json", {}), "early": js.EARLY, "generators": _generators(),
            "outputs": {s: {k: None if p is None else _read_json(p) for k, p in kinds.items()}
                        for s, kinds in outputs.items()}}
    h.send_json(200, body, {"ETag": etag})
    return None


def r_inbox(h, q):
    body = h.json_body()
    folder = h.job_folder(body.get("folder"))
    event = body.get("event")
    if not isinstance(event, dict):
        raise HttpError(400, "event must be an object")
    return js.append_event(folder, event)


def r_gui(h, q):
    body = h.json_body()
    folder = h.job_folder(body.get("folder"))
    patch = body.get("patch")
    if not isinstance(patch, dict):
        raise HttpError(400, "patch must be an object")
    path = js.state_dir(folder) / "gui.json"
    with js.lock(folder):
        data = _read_json(path, {})
        data = data if isinstance(data, dict) else {}
        for key, value in patch.items():
            if value is None:
                data.pop(key, None)
            else:
                data[key] = value
        js.write_json_atomic(path, data)
    return data


def r_new(h, q):
    body = h.json_body()
    client, product, raw = _need_str(body, "client"), _need_str(body, "product"), _need_str(body, "folder")
    root = h.server.root
    folder = h.video_folder(str(Path(raw) if Path(raw).is_absolute() else Path(root) / raw))
    if not folder.parent.is_dir():
        raise HttpError(400, f"{folder.parent.name} does not exist yet; only the video folder itself is created")
    with js.lock(folder):
        if (js.state_dir(folder) / "job.json").exists():
            raise HttpError(409, "this folder already has a job")
        folder.mkdir(exist_ok=True)  # the video folder only, never its parents
        job = js.new_job(folder, client, product)
        js.save(folder, job)
    js.set_current(folder)
    return {"folder": folder.as_posix(), "job": job}


def _check_name(name: str) -> None:
    if (not name or len(name) > 255 or name.startswith(".") or name.endswith((".", " "))
            or any(c in name for c in '/\\:<>"|?*\0') or any(ord(c) < 32 for c in name)
            or name.split(".")[0].strip().lower() in RESERVED):
        raise HttpError(400, f"not an allowed file name: {name!r}")


def _free_name(folder: Path, name: str) -> Path:
    stem, suffix = Path(name).stem, Path(name).suffix
    dest, n = folder / name, 2
    while dest.exists():
        dest, n = folder / f"{stem} ({n}){suffix}", n + 1
    return dest


def r_upload(h, q):
    folder = h.job_folder(q.get("folder"))
    kind = q.get("kind")
    if kind not in UPLOADS:
        raise HttpError(400, f"kind must be one of {', '.join(UPLOADS)}")
    sub, step, exts, limit = UPLOADS[kind]
    name = q.get("name", "")
    _check_name(name)
    ext = Path(name).suffix[1:].lower()
    if ext not in exts:
        raise HttpError(415, f"That file type can't go here. Allowed: {', '.join(sorted(exts))}.")
    kid = q.get("id", "")
    if kind == "keyframe" and not KEYFRAME_ID.fullmatch(kid):
        raise HttpError(400, "keyframe id must look like SB-1 or CHAR-1")
    length = h.content_length()
    if length > limit:
        raise HttpError(413, f"That file is too big (the limit here is {limit // MIB} MiB).")
    target = folders.safe_path(folder / sub, [folder])  # a symlinked refs/ vo/ music/ storyboard/ can't lead out
    target.mkdir(parents=True, exist_ok=True)
    part = target / f".upload-{uuid.uuid4().hex}.part"
    try:
        h.read_body_to(part, length)
        with _upload_lock:
            if kind == "keyframe":
                dest = target / f"{kid}.{ext}"
                os.replace(part, dest)
                for other in KEYFRAME_EXTS - {ext}:  # a replaced keyframe keeps a single file
                    (target / f"{kid}.{other}").unlink(missing_ok=True)
            else:
                dest = _free_name(target, name)
                os.replace(part, dest)
    finally:
        part.unlink(missing_ok=True)
    saved = dest.resolve().as_posix()
    event = js.append_event(folder, {"type": "upload", "step": step,
                                     "target": f"{kind}:{kid if kind == 'keyframe' else name}", "value": saved})
    return {"path": saved, "event": event}


def r_file(h, q):
    path = h.safe(q.get("path"), [h.server.root, h.server.tmp])
    if not path.is_file():
        raise HttpError(404, "file not found")
    # sandbox: an HTML or SVG file from a video folder runs in an opaque origin, never with the API token
    h.send_file(path, {"Content-Security-Policy": "sandbox allow-scripts"})
    return None


def _settings_file() -> dict:
    cfg = Path(machine.CONFIG)
    if not cfg.exists():
        return {}
    data = json.loads(cfg.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{cfg} is not a JSON object")
    return data


def r_settings(h, q):
    saved = _settings_file()
    paths = {k: saved.get(k, machine.PATHS.get(k)) for k in SETTINGS_KEYS}
    paths["gui_port"] = paths["gui_port"] or DEFAULT_PORT
    found = {k: bool(paths[k]) and (Path(paths[k]).is_dir() if is_dir else Path(paths[k]).is_file())
             for k, is_dir in SETTINGS_DIRS.items()}
    running = {"root": Path(h.server.root).as_posix(), "tmp": Path(h.server.tmp).as_posix(),
               "port": h.server.server_address[1]}
    return {"config": Path(machine.CONFIG).as_posix(), "paths": paths, "found": found, "running": running}


def r_settings_save(h, q):
    body = h.json_body()
    update = {}
    for key in SETTINGS_KEYS:
        if key not in body:
            continue
        value = body[key]
        if key == "gui_port":
            if isinstance(value, bool) or not isinstance(value, int) or not 1024 <= value <= 65535:
                raise HttpError(400, "gui_port must be a number from 1024 to 65535")
        elif not isinstance(value, str) or not value.strip() or len(value) > 1024:
            raise HttpError(400, f"{key} must be a path")
        elif not Path(value.strip()).exists():
            raise HttpError(400, f"{key}: {value.strip()} does not exist on this computer")
        elif key == "python" and Path(value.strip()).name.lower() not in PYTHON_NAMES:  # /api/checks runs it
            raise HttpError(400, f"python must be a Python executable ({', '.join(sorted(PYTHON_NAMES))})")
        update[key] = value.strip() if isinstance(value, str) else value
    data = _settings_file()  # keeps keys already in the file (_note, asr, ...)
    data.update(update)
    js.write_json_atomic(Path(machine.CONFIG), data)
    return r_settings(h, q)


def _gui_dir(h) -> Path:
    return Path(h.server.tmp) / "gui"


def r_prefs(h, q):
    return js.read_prefs(_gui_dir(h) / "prefs.json")


def r_prefs_save(h, q):
    try:  # known keys and values only (jobstate.PREFS); the same lock as `job.py lang`
        return js.update_prefs(_gui_dir(h), h.json_body())
    except ValueError as e:
        raise HttpError(400, str(e)) from None


PRACTICE = "/practice-muna"
PRACTICE_GAP = 10.0      # seconds: a second click within this gets "busy", so a double click opens one window
PRACTICE_TIMEOUT = 120   # seconds osascript may take (the first time macOS may ask to let it control Terminal)
CREATE_NEW_CONSOLE = 0x10  # Windows creation flag (subprocess.CREATE_NEW_CONSOLE exists only on Windows)
_practice_lock = threading.Lock()


def _platform() -> str:
    return sys.platform


def _clock() -> float:
    return time.monotonic()


def _applescript_text(s: str) -> str:
    """s inside an AppleScript string literal: backslash and double quote escaped."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def practice_argv(root: Path, platform: str) -> "list[str] | None":
    """The fixed launch command for this system, or None where the app can't open a window (Linux, ...).
    macOS: the shell line `cd <root> && claude '/practice-muna'` (root shlex-quoted) in a new Terminal window, inside
    an AppleScript string (escaped for it), then Terminal comes to the front. Windows: a new console (CREATE_NEW_CONSOLE)
    running `claude /practice-muna`; the root is its working directory (cwd), never text on the command line."""
    if platform == "darwin":
        line = f"cd {shlex.quote(str(root))} && claude '{PRACTICE}'"
        return ["osascript", "-e", f'tell application "Terminal" to do script "{_applescript_text(line)}"',
                "-e", 'tell application "Terminal" to activate']
    if platform == "win32":
        return ["cmd", "/k", f"claude {PRACTICE}"]
    return None


def _launch(argv: "list[str]", root: Path, platform: str) -> str:
    """Start the window: "ok", "refused" (osascript ran and exited non-zero, e.g. Automation not allowed) or "failed"
    (it could not start or timed out). Windows: Popen with only cwd and CREATE_NEW_CONSOLE, no wait; no stdio arguments,
    so cmd and claude get the new console itself (DEVNULL would hand them NUL and the window would close), and no pipes
    that would keep the request open until the editor closed Claude."""
    try:
        if platform == "win32":
            subprocess.Popen(argv, cwd=str(root), creationflags=CREATE_NEW_CONSOLE)
            return "ok"
        done = subprocess.run(argv, cwd=str(root), timeout=PRACTICE_TIMEOUT, capture_output=True,
                              stdin=subprocess.DEVNULL)
        return "ok" if done.returncode == 0 else "refused"
    except (OSError, subprocess.SubprocessError):
        return "failed"


def r_practice(h, q):
    h.discard_body()  # the request carries nothing this route uses
    root, platform = Path(h.server.root), _platform()
    argv = practice_argv(root, platform)
    if argv is None:
        return {"ok": False, "reason": "unsupported"}
    if any(ord(c) < 32 for c in str(root)):  # a control character can't go on a command line safely
        return {"ok": False, "reason": "failed"}
    with _practice_lock:
        now = _clock()
        last = getattr(h.server, "practice_at", None)
        if getattr(h.server, "practice_running", False) or (last is not None and now - last < PRACTICE_GAP):
            return {"ok": False, "reason": "busy"}
        if not shutil.which("claude"):
            return {"ok": False, "reason": "no-claude"}
        h.server.practice_at, h.server.practice_running = now, True
    outcome = "failed"
    try:
        outcome = _launch(argv, root, platform)
    finally:
        with _practice_lock:
            h.server.practice_running = False
            if outcome != "ok":
                h.server.practice_at = None  # a failed launch never makes the retry say "busy"
    if outcome == "ok":
        return {"ok": True}
    # the Automation hint only when osascript really ran and said no (not when it is missing or timed out)
    return {"ok": False, "reason": "failed", **({"hint": "automation"} if outcome == "refused" and platform == "darwin" else {})}


def r_checks(h, q):
    return checks.setup()


def r_capcut(h, q):
    return {"running": checks.capcut_running()}


def r_temp_en(h, q):
    roots = [r for r in (h.server.root, h.server.tmp, machine.PATHS.get("capcut_drafts")) if r]
    project = h.safe(q.get("project"), roots)
    try:  # never "clean" for a project that isn't there or can't be read: the page says it could not check
        checks.capcut_project.list_timelines(project)
    except (OSError, ValueError, KeyError):
        raise HttpError(404, f"no readable CapCut project at {project.as_posix()}") from None
    return {"timelines": checks.temp_en_timelines(project)}


def r_feedback(h, q):
    return feedback.items(h.server.root)


def r_feedback_save(h, q):
    root = h.server.root
    entry = feedback.save(h.json_body(), root)
    return {**entry, "issue_url": feedback.issue_url(entry, feedback.version(root), feedback.os_name())}


ROUTES = {  # (method, path): (handler, needs token)
    ("GET", "/api/ping"): (r_ping, False),
    ("GET", "/api/jobs"): (r_jobs, True),
    ("GET", "/api/current"): (r_current, True),
    ("GET", "/api/job"): (r_job, True),
    ("POST", "/api/inbox"): (r_inbox, True),
    ("POST", "/api/gui"): (r_gui, True),
    ("POST", "/api/new"): (r_new, True),
    ("PUT", "/api/upload"): (r_upload, True),
    ("GET", "/api/file"): (r_file, True),
    ("GET", "/api/settings"): (r_settings, True),
    ("POST", "/api/settings"): (r_settings_save, True),
    ("GET", "/api/prefs"): (r_prefs, True),
    ("POST", "/api/prefs"): (r_prefs_save, True),
    ("GET", "/api/checks"): (r_checks, True),
    ("GET", "/api/capcut"): (r_capcut, True),
    ("GET", "/api/temp-en"): (r_temp_en, True),
    ("GET", "/api/feedback"): (r_feedback, True),
    ("POST", "/api/feedback"): (r_feedback_save, True),
    ("POST", "/api/practice"): (r_practice, True),
}


class Handler(BaseHTTPRequestHandler):
    server_version = APP

    def log_message(self, format, *args):  # quiet: no per-request stderr lines
        pass

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_PUT(self):
        self._handle("PUT")

    # ----- plumbing -----

    def _handle(self, method: str) -> None:
        self._sent = False
        try:
            url = urlsplit(self.path)
            self._guard()
            q = {k: v[-1] for k, v in parse_qs(url.query).items()}
            route = ROUTES.get((method, url.path))
            if route is None:
                if method == "GET" and (url.path == "/" or url.path.startswith("/static/")):
                    return self._static(url.path, q)
                raise HttpError(404, "not found")
            fn, needs_token = route
            if needs_token and not self._token_ok():
                raise HttpError(401, "missing or wrong token; open the link the server printed")
            result = fn(self, q)
            if result is not None:
                self.send_json(200, result)
        except (ConnectionError, TimeoutError):
            self.close_connection = True
        except Exception as e:  # noqa: BLE001 - every error becomes a JSON reply
            status = (e.status if isinstance(e, HttpError) else 403 if isinstance(e, PermissionError)
                      else 404 if isinstance(e, FileNotFoundError) else 400 if isinstance(e, (ValueError, TypeError))
                      else 500)
            message = e.message if isinstance(e, HttpError) else str(e) or type(e).__name__
            if not self._sent:
                self.send_json(status, {"error": message})
            self.close_connection = True

    def _guard(self) -> None:
        port = self.server.server_address[1]
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if (self.headers.get("Host") or "").lower() not in hosts:
            raise HttpError(403, "wrong host")
        origin = self.headers.get("Origin")
        if origin is not None and origin.lower() not in {f"http://{h}" for h in hosts}:
            raise HttpError(403, "foreign origin")

    def _token_ok(self, given: "str | None" = None) -> bool:
        if given is None:
            given = self.headers.get("X-EMT-Token")
        if given is None:
            jar = cookies.SimpleCookie()
            try:
                jar.load(self.headers.get("Cookie") or "")
            except cookies.CookieError:
                pass
            given = jar["emt"].value if "emt" in jar else None
        return given is not None and hmac.compare_digest(given.encode("utf-8"), self.server.token.encode("utf-8"))

    def _static(self, path: str, q: dict) -> None:
        if path == "/" and "k" in q:
            if not self._token_ok(q["k"]):
                raise HttpError(401, "wrong token")
            cookie = f"emt={self.server.token}; HttpOnly; SameSite=Strict; Path=/"
            return self.reply(302, b"", None, {"Location": "/", "Set-Cookie": cookie})
        rel = "index.html" if path == "/" else unquote(path[len("/static/"):])
        target = folders.safe_path(STATIC / rel, [STATIC])
        if not target.is_file():
            raise HttpError(404, "not found")
        self.send_file(target)

    def reply(self, status: int, data: bytes, ctype: "str | None", extra: "dict | None" = None) -> None:
        self.send_response(status)
        if ctype:
            self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self._sent = True
        if data:
            self.wfile.write(data)

    def send_json(self, status: int, obj, extra: "dict | None" = None) -> None:
        self.reply(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8", extra)

    def send_file(self, path: Path, extra: "dict | None" = None) -> None:
        with path.open("rb") as f:
            size = os.fstat(f.fileno()).st_size
            self.send_response(200)
            self.send_header("Content-Type", _content_type(path))
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self._sent = True
            while chunk := f.read(CHUNK):
                self.wfile.write(chunk)

    def content_length(self) -> int:
        if self.headers.get("Transfer-Encoding"):
            raise HttpError(411, "send a Content-Length (chunked bodies are not accepted)")
        raw = self.headers.get("Content-Length")
        if raw is None:
            raise HttpError(411, "Content-Length is required")
        if not raw.strip().isdigit():
            raise HttpError(400, "bad Content-Length")
        return int(raw)

    def discard_body(self) -> None:
        """Read and drop a request body (so the connection stays in step); its content is never looked at."""
        if self.headers.get("Transfer-Encoding"):
            self.close_connection = True  # not read: the connection ends after this reply
        raw = self.headers.get("Content-Length")
        length = int(raw) if raw and raw.strip().isdigit() else 0
        if length > MAX_JSON:
            raise HttpError(413, "request body too big")
        if length:
            self.rfile.read(length)

    def json_body(self) -> dict:
        length = self.content_length()
        if length > MAX_JSON:
            raise HttpError(413, "request body too big")
        data = json.loads(self.rfile.read(length).decode("utf-8") or "null")
        if not isinstance(data, dict):
            raise HttpError(400, "body must be a JSON object")
        return data

    def read_body_to(self, path: Path, length: int) -> None:
        """Stream exactly `length` body bytes into path, CHUNK at a time."""
        remaining = length
        with path.open("wb") as f:
            while remaining:
                chunk = self.rfile.read(min(CHUNK, remaining))
                if not chunk:
                    raise HttpError(400, "the upload ended early")
                f.write(chunk)
                remaining -= len(chunk)

    def safe(self, raw, roots) -> Path:
        if not isinstance(raw, str) or not raw:
            raise HttpError(400, "a path is required")
        return folders.safe_path(raw, roots)

    def video_folder(self, raw) -> Path:
        """An absolute path that is a video folder of root by the folders.py rule (it may not exist yet)."""
        if isinstance(raw, str) and raw and not Path(raw).is_absolute():
            raise HttpError(400, "folder must be an absolute path")
        folder = self.safe(raw, [self.server.root])
        if not folders.is_video_folder(folder, self.server.root):
            raise HttpError(403, "not a video folder (a direct subfolder of the root, or _practice/<name>)")
        return folder

    def job_folder(self, raw) -> Path:
        """A video folder that already has a job.json."""
        folder = self.video_folder(raw)
        if not (js.state_dir(folder) / "job.json").is_file():
            raise HttpError(404, "no job in this folder")
        return folder


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = sys.platform != "win32"  # on Windows SO_REUSEADDR would share a port in use

    def handle_error(self, request, client_address):
        if not isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError)):
            super().handle_error(request, client_address)


def make_server(port: int, root: Path, tmp: Path, token: str) -> ThreadingHTTPServer:
    srv = _Server(("127.0.0.1", port), Handler)
    srv.root, srv.tmp, srv.token = Path(root), Path(tmp), token
    return srv


def _ours(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=1) as r:
            return json.loads(r.read()).get("app") == APP
    except (OSError, ValueError):
        return False


def main(argv: "list[str] | None" = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--port", type=int)
    p.add_argument("--root", help="video root instead of {root} from machine.json (launch.py and tests)")
    p.add_argument("--tmp", help="state folder instead of {tmp} from machine.json (launch.py and tests)")
    a = p.parse_args(argv)
    paths = machine.PATHS
    root, tmp = Path(a.root or paths["root"]), Path(a.tmp or paths["tmp"])
    first = a.port or int(paths.get("gui_port") or DEFAULT_PORT)
    token, srv = secrets.token_urlsafe(24), None
    for port in range(first, first + 20):
        try:
            srv = make_server(port, root, tmp, token)
            break
        except OSError:  # taken: by our own server (reuse it), or by something else (try the next port)
            if _ours(port):
                print(json.dumps({"ok": True, "already_running": True, "port": port}), flush=True)
                return
    if srv is None:
        print(json.dumps({"ok": False, "error": f"no free port from {first} to {first + 19}"}), flush=True)
        sys.exit(1)
    port = srv.server_address[1]
    info = tmp / "gui" / "server.json"
    js.write_json_atomic(info, {"pid": os.getpid(), "port": port, "token": token, "version": API_VERSION})
    print(json.dumps({"ok": True, "url": f"http://127.0.0.1:{port}/?k={token}", "port": port}), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
        if (_read_json(info) or {}).get("pid") == os.getpid():
            info.unlink(missing_ok=True)


if __name__ == "__main__":
    main(sys.argv[1:])
