"""Start the companion GUI server, or reuse the one already running, and print how to open it.

    run gui/launch.py [--folder F] [--open] [--port P]

Prints one JSON line {"url": "http://127.0.0.1:<port>/?k=<token>", "port": N, "reused": bool}, or exits 1 with
{"ok": false, "error": ...}. Port: --port, else gui_port from machine.json, else 4810 (then +1 ... +10).
Reuse needs {tmp}/gui/server.json with a live pid whose port answers /api/ping as our app, same version.
Our own older or unresponsive server is stopped and replaced on its port; a foreign program on a port is never
touched (the next port is tried). The new server is detached: it outlives this command. --folder makes that
folder the current job; --open also opens the URL in the browser.
"""
import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

GUI = Path(__file__).resolve().parent
for _p in (GUI, GUI.parent / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import jobstate as js  # noqa: E402
import machine  # noqa: E402
import server  # noqa: E402

PORT_TRIES = 11  # the first port and the next ten


def _tmp() -> Path:
    return Path(os.environ.get("EDIT_MO_TO_GUI_TMP") or machine.PATHS["tmp"])


def _read_info(tmp: Path) -> "dict | None":
    try:
        data = json.loads((tmp / "gui" / "server.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and isinstance(data.get("pid"), int) else None
    except (OSError, ValueError):
        return None


def _ping(port: int) -> "dict | None":
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=1) as r:
            data = json.loads(r.read())
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _current(port: int) -> bool:
    ans = _ping(port)
    return bool(ans) and ans.get("app") == server.APP and ans.get("version") == server.API_VERSION


def _port_free(port: int) -> bool:
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _terminate(pid: int) -> str:
    """Stop pid (and its children on Windows); returns "" or a note about what went wrong."""
    if sys.platform == "win32":
        r = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        return "" if r.returncode == 0 else f"taskkill exit code {r.returncode}"
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as e:
        return f"kill failed: {e}"
    deadline = time.time() + 3
    while time.time() < deadline and js.pid_alive(pid):
        time.sleep(0.1)
    if js.pid_alive(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError as e:
            return f"kill failed: {e}"
    return ""


def _wait_free(port: int, seconds: float = 5) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if _port_free(port):
            return True
        time.sleep(0.2)
    return _port_free(port)


def _usable(info: "dict | None") -> bool:
    return bool(info) and isinstance(info.get("port"), int) and isinstance(info.get("token"), str)         and _current(info["port"])


def _start(port: int, tmp: Path) -> "dict | None":
    """Spawn server.py detached on `port`; return its server.json once it answers /api/ping, else None."""
    info = _read_info(tmp)
    if not (info and js.pid_alive(info["pid"])):  # never remove a server.json that names a live process
        (tmp / "gui" / "server.json").unlink(missing_ok=True)
    kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
              "close_fds": True}
    if sys.platform == "win32":
        kwargs["creationflags"] = (subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
                                   | subprocess.CREATE_NO_WINDOW)
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen([sys.executable, str(GUI / "server.py"), "--port", str(port), "--tmp", str(tmp)],
                            **kwargs)
    deadline = time.time() + 10
    while time.time() < deadline:
        exited = proc.poll() is not None  # on Windows the venv launcher may exit 0 early: look once more, then stop
        info = _read_info(tmp)
        if _usable(info):
            return info
        if exited:
            break
        time.sleep(0.2)
    return None


class _Lock:
    """Exclusive-create lock file {tmp}/gui/launch.lock so two launches never start two servers."""

    def __init__(self, tmp: Path):
        self.path = tmp / "gui" / "launch.lock"

    def _stale(self) -> bool:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return time.time() - float(data["time"]) > 30 or not js.pid_alive(int(data["pid"]))
        except (OSError, ValueError, KeyError, TypeError):
            try:
                return time.time() - self.path.stat().st_mtime > 30  # half-written or unreadable
            except OSError:
                return False

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.time() + 15
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if self._stale():
                    self.path.unlink(missing_ok=True)
                    continue
                if time.time() > deadline:
                    raise RuntimeError("another launch is still running (launch.lock)")
                time.sleep(0.1)
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"pid": os.getpid(), "time": time.time()}, f)
            return self

    def __exit__(self, *exc):
        self.path.unlink(missing_ok=True)


def _url(info: dict) -> str:
    return f"http://127.0.0.1:{info['port']}/?k={info['token']}"


def launch(first: int, tmp: Path) -> "tuple[dict, bool]":
    """(server.json info, reused). Raises RuntimeError with a plain message when nothing could start."""
    with _Lock(tmp):
        return _launch(first, tmp)


def _launch(first: int, tmp: Path) -> "tuple[dict, bool]":
    info = _read_info(tmp)
    stale_port, note = None, ""
    if info and js.pid_alive(info["pid"]) and isinstance(info.get("port"), int):
        ans = _ping(info["port"])
        if _usable(info):
            return info, True
        if ans and ans.get("app") == server.APP and ans.get("version") != server.API_VERSION:
            note = _terminate(info["pid"])  # our own older server: the only thing this ever stops
            if _wait_free(info["port"]):
                stale_port = info["port"]
            else:
                raise RuntimeError(f"the old GUI server (pid {info['pid']}) did not release port "
                                   f"{info['port']}" + (f" ({note})" if note else ""))
    if info:  # stale record (dead pid, silent port, foreign app, replaced server): drop it, kill nothing else
        (tmp / "gui" / "server.json").unlink(missing_ok=True)
    candidates = ([stale_port] if stale_port else []) + [p for p in range(first, first + PORT_TRIES)
                                                         if p != stale_port]
    for port in candidates:
        if not _port_free(port):  # a foreign program (or something else): leave it alone
            continue
        started = _start(port, tmp)
        if started:
            return started, False
    raise RuntimeError(f"could not start the GUI server on ports {first} to {first + PORT_TRIES - 1}")


def main(argv: "list[str] | None" = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--folder")
    p.add_argument("--open", action="store_true")
    p.add_argument("--port", type=int)
    a = p.parse_args(argv)
    try:
        first = a.port or int(machine.PATHS.get("gui_port") or server.DEFAULT_PORT)
        info, reused = launch(first, _tmp())
    except (RuntimeError, ValueError, TypeError) as e:
        print(json.dumps({"ok": False, "error": str(e)}), flush=True)
        sys.exit(1)
    if a.folder:
        js.set_current(Path(a.folder).resolve())
    url = _url(info)
    print(json.dumps({"url": url, "port": info["port"], "reused": reused}), flush=True)
    if a.open:
        webbrowser.open(url)


if __name__ == "__main__":
    main(sys.argv[1:])
