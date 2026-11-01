"""Block until the editor answers in the companion GUI. Claude runs this in the background at a gate.

    wait.py <folder> [--after N] [--step S] [--timeout SECONDS] [--poll 0.5]
    wait.py --app [--timeout SECONDS] [--poll 0.5]

--app: listen on the app itself, before any video exists (Claude opened the app on its dashboard). Writes
{tmp}/gui/attached.json as the heartbeat, so the app's Submit to Claude and Resume hand the video to this Claude
instead of opening a second one, and exits 0 with {"folder": "<video>", "events": [...]} once the current video has
an unhandled `brief:submit` or `app:resume` (the other exits below apply too, except 6).

Writes <folder>/.edit-mo-to/listening.json (the GUI shows "Claude is listening") and refreshes it on
every poll as a heartbeat. Prints exactly one JSON line on stdout and exits:
    0    {"events": [...]}      new inbox events with seq > N
    3    {"events": []}         --timeout elapsed (0, the default, waits forever)
    4    {"superseded": true}   another live wait.py took over the listening file
    5    {"orphaned": true}     the process that started it is gone (POSIX: Claude Code quit), so no
                                 orphan keeps a false "Claude is listening"
    6    {"gone": true}         the video was deleted (its folder, or the job.json it had at start, is gone): it
                                 never comes back, because a waiter never creates a deleted folder again
    130  (no output)            Ctrl+C / SIGTERM / SIGBREAK
The listening file is cleared on exit only if it still names this process.
"""
import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jobstate as js  # noqa: E402


def _owner(folder: Path) -> int | None:
    try:
        return int(json.loads(js._listening_path(folder).read_text(encoding="utf-8"))["pid"])
    except (OSError, ValueError, TypeError, KeyError):
        return None


def _superseded(folder: Path) -> bool:
    pid = _owner(folder)
    return pid is not None and pid != os.getpid() and js.pid_alive(pid)


def _release(folder: Path) -> None:
    if _owner(folder) == os.getpid():
        js.clear_listening(folder)


def _heartbeat(folder: Path, step: str | None) -> bool:
    """Refresh our listening.json unless another live waiter took over. The temp file is written
    first and the owner re-checked just before the atomic replace, so a take-over that lands
    mid-heartbeat is not overwritten (window: one os.replace). Returns False if superseded."""
    path = js._listening_path(folder)
    since = js._now()
    try:
        old = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(old, dict) and old.get("pid") == os.getpid() and old.get("since"):
            since = old["since"]
    except (OSError, ValueError):
        pass
    tmp = path.with_name(f"{path.name}.{os.getpid()}.hb.tmp")
    try:
        tmp.write_text(json.dumps({"pid": os.getpid(), "since": since, "beat": time.time(), "step": step},
                                  ensure_ascii=False), encoding="utf-8")
        if _superseded(folder):
            return False
        js._retry(lambda: os.replace(tmp, path))
        return True
    finally:
        tmp.unlink(missing_ok=True)


def _orphaned(parent: int) -> bool:
    """POSIX: our parent changed since start (we were reparented to init/launchd or a subreaper), so whoever started
    us is gone. A waiter started detached (parent already 1) is left alone. Windows never reparents: always False
    (there `job.py stop-wait` stops a waiter, and a deleted video stops it by itself: exit 6)."""
    return sys.platform != "win32" and os.getppid() != parent


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _gone(folder: Path, had_job: bool) -> bool:
    """The video was deleted: its folder is gone, or the job it had when we started is gone."""
    return not folder.is_dir() or (had_job and not (js.state_dir(folder) / "job.json").is_file())


def wait(folder: Path, after: int, step: str | None, timeout: float, poll: float) -> int:
    deadline = time.monotonic() + timeout if timeout > 0 else None
    parent = os.getppid()
    if not folder.is_dir():
        _emit({"gone": True})
        return 6
    had_job = (js.state_dir(folder) / "job.json").is_file()
    try:
        js.write_listening(folder, step)  # a new waiter always takes over
        while True:
            if _gone(folder, had_job):
                _emit({"gone": True})
                return 6
            events = js.read_events(folder, after)
            if events:
                _emit({"events": events})
                return 0
            if deadline is not None and time.monotonic() >= deadline:
                _emit({"events": []})
                return 3
            if _orphaned(parent):
                _emit({"orphaned": True})
                return 5
            if not _heartbeat(folder, step):
                _emit({"superseded": True})
                return 4
            time.sleep(poll)
    finally:
        _release(folder)


APP_WAKE = ("brief:submit", "app:resume")  # the actions that hand the current video to the attached Claude


def _attach_owner() -> int | None:
    try:
        return int(json.loads(js._attached_path().read_text(encoding="utf-8"))["pid"])
    except (OSError, ValueError, TypeError, KeyError):
        return None


def _app_ready() -> dict | None:
    """The current video, once it has an unhandled brief:submit or app:resume: {"folder", "events"} (every unhandled
    event, so Claude reads them all), else None."""
    folder = js.get_current()
    if not folder or not (js.state_dir(Path(folder)) / "job.json").is_file():
        return None
    events = js.unhandled(Path(folder))
    if any(e.get("type") == "action" and e.get("target") in APP_WAKE for e in events):
        return {"folder": Path(folder).as_posix(), "events": events}
    return None


def wait_app(timeout: float, poll: float) -> int:
    deadline = time.monotonic() + timeout if timeout > 0 else None
    parent, path, since = os.getppid(), js._attached_path(), js._now()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        while True:
            owner = _attach_owner()
            if owner is not None and owner != os.getpid() and js.pid_alive(owner) and js.attached() is not None                     and json.loads(path.read_text(encoding="utf-8")).get("since", "") > since:
                _emit({"superseded": True})  # a newer Claude listens on the app now
                return 4
            js._write_atomic(path, json.dumps({"pid": os.getpid(), "since": since, "beat": time.time()}))
            ready = _app_ready()
            if ready:
                _emit(ready)
                return 0
            if deadline is not None and time.monotonic() >= deadline:
                _emit({"events": []})
                return 3
            if _orphaned(parent):
                _emit({"orphaned": True})
                return 5
            time.sleep(poll)
    finally:
        if _attach_owner() == os.getpid():
            path.unlink(missing_ok=True)


def _interrupt(signum, frame):
    raise KeyboardInterrupt


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Wait for the editor's answer in the GUI.")
    ap.add_argument("folder", nargs="?")
    ap.add_argument("--app", action="store_true", help="listen on the app itself (no video yet)")
    ap.add_argument("--after", type=int, default=0)
    ap.add_argument("--step", default=None)
    ap.add_argument("--timeout", type=float, default=0.0, help="seconds; 0 = wait forever")
    ap.add_argument("--poll", type=float, default=0.5)
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    if args.app == bool(args.folder):
        ap.error("give a video folder, or --app")
    for name in ("SIGTERM", "SIGBREAK"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), _interrupt)
    try:
        if args.app:
            return wait_app(args.timeout, max(args.poll, 0.01))
        return wait(Path(args.folder).resolve(), args.after, args.step, args.timeout, max(args.poll, 0.01))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
