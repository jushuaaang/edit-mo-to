"""Block until the editor answers in the companion GUI. Claude runs this in the background at a gate.

    wait.py <folder> [--after N] [--step S] [--timeout SECONDS] [--poll 0.5]

Writes <folder>/.edit-mo-to/listening.json (the GUI shows "Claude is listening") and refreshes it on
every poll as a heartbeat. Prints exactly one JSON line on stdout and exits:
    0    {"events": [...]}      new inbox events with seq > N
    3    {"events": []}         --timeout elapsed (0, the default, waits forever)
    4    {"superseded": true}   another live wait.py took over the listening file
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
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def wait(folder: Path, after: int, step: str | None, timeout: float, poll: float) -> int:
    deadline = time.monotonic() + timeout if timeout > 0 else None
    try:
        js.write_listening(folder, step)  # a new waiter always takes over
        while True:
            events = js.read_events(folder, after)
            if events:
                _emit({"events": events})
                return 0
            if deadline is not None and time.monotonic() >= deadline:
                _emit({"events": []})
                return 3
            if not _heartbeat(folder, step):
                _emit({"superseded": True})
                return 4
            time.sleep(poll)
    finally:
        _release(folder)


def _interrupt(signum, frame):
    raise KeyboardInterrupt


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Wait for the editor's answer in the GUI.")
    ap.add_argument("folder")
    ap.add_argument("--after", type=int, default=0)
    ap.add_argument("--step", default=None)
    ap.add_argument("--timeout", type=float, default=0.0, help="seconds; 0 = wait forever")
    ap.add_argument("--poll", type=float, default=0.5)
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    folder = Path(args.folder).resolve()
    for name in ("SIGTERM", "SIGBREAK"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), _interrupt)
    try:
        return wait(folder, args.after, args.step, args.timeout, max(args.poll, 0.01))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
