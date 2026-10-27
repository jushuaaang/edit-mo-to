import json
import os
import random
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

GUI = Path(__file__).resolve().parents[2] / "gui"
LAUNCH = GUI / "launch.py"
sys.path.insert(0, str(GUI))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jobstate as js  # noqa: E402


def free_port() -> int:
    """A random high port whose next 11 neighbours are free too (the launcher scans port+1 .. port+10)."""
    for _ in range(100):
        port = random.randint(20000, 40000)
        try:
            for p in range(port, port + 12):
                with socket.socket() as s:
                    s.bind(("127.0.0.1", p))
            return port
        except OSError:
            continue
    raise RuntimeError("no free port")


def kill(pid: int) -> None:
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        try:
            os.kill(pid, 9)
        except OSError:
            pass


def info_pid(tmp: Path):
    try:
        return json.loads((tmp / "gui" / "server.json").read_text(encoding="utf-8"))["pid"]
    except (OSError, ValueError, KeyError):
        return None


@pytest.fixture
def env(tmp_path, monkeypatch):
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    monkeypatch.setenv("EDIT_MO_TO_GUI_TMP", str(tmp))
    yield tmp
    pid = info_pid(tmp)
    if pid:
        kill(pid)


def launch(*args):
    r = subprocess.run([sys.executable, str(LAUNCH), *args], capture_output=True, text=True,
                       encoding="utf-8", timeout=60)
    return r, (json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else None)


def ping(port):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=2) as r:
        return json.loads(r.read())


def test_starts_then_reuses(env):
    port = free_port()
    r1, a = launch("--port", str(port))
    assert r1.returncode == 0, r1.stderr
    assert a["reused"] is False and a["port"] == port
    token = json.loads((env / "gui" / "server.json").read_text(encoding="utf-8"))["token"]
    assert a["url"] == f"http://127.0.0.1:{port}/?k={token}"
    assert ping(port) == {"app": "edit-mo-to-gui", "version": 1}
    r2, b = launch("--port", str(port))
    assert b["reused"] is True and b["url"] == a["url"]


def test_folder_sets_current(env, tmp_path):
    folder = tmp_path / "vid"
    folder.mkdir()
    r, a = launch("--port", str(free_port()), "--folder", str(folder))
    assert r.returncode == 0, r.stderr
    assert js.get_current() == folder.resolve().as_posix()


def test_foreign_server_on_port_moves_to_next(env):
    port = free_port()

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"hello")

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        r, a = launch("--port", str(port))
        assert r.returncode == 0, r.stderr
        assert a["port"] == port + 1 and a["reused"] is False
        assert ping(port + 1)["app"] == "edit-mo-to-gui"
    finally:
        srv.shutdown()
        srv.server_close()


def test_old_version_restarts(env):
    port = free_port()
    stub_code = (
        "import json\nfrom http.server import BaseHTTPRequestHandler, HTTPServer\n"
        "class H(BaseHTTPRequestHandler):\n"
        "    def do_GET(self):\n"
        "        b = json.dumps({'app': 'edit-mo-to-gui', 'version': 0}).encode()\n"
        "        self.send_response(200); self.send_header('Content-Length', str(len(b)))\n"
        "        self.end_headers(); self.wfile.write(b)\n"
        "    def log_message(self, *a): pass\n"
        f"HTTPServer(('127.0.0.1', {port}), H).serve_forever()\n")
    proc = subprocess.Popen([sys.executable, "-c", stub_code])
    try:
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                if ping(port)["version"] == 0:
                    break
            except OSError:
                time.sleep(0.1)
        assert ping(port)["version"] == 0
        js.write_json_atomic(env / "gui" / "server.json",
                             {"pid": proc.pid, "port": port, "token": "old", "version": 0})
        r, a = launch("--port", str(port + 5))
        assert r.returncode == 0, r.stderr
        assert a["port"] == port and a["reused"] is False
        assert ping(port)["version"] == 1
        proc.wait(timeout=10)  # the stub was terminated
    finally:
        proc.kill()
