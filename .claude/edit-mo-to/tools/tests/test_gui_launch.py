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
import server  # noqa: E402


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
    pong = ping(port)
    assert pong["app"] == "edit-mo-to-gui" and pong["version"] == server.API_VERSION
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
        "        b = json.dumps({'app': 'edit-mo-to-gui', 'version': 0, 'pid': __import__('os').getpid()}).encode()\n"
        "        self.send_response(200); self.send_header('Content-Length', str(len(b)))\n"
        "        self.end_headers(); self.wfile.write(b)\n"
        "    def log_message(self, *a): pass\n"
        f"HTTPServer(('127.0.0.1', {port}), H).serve_forever()\n")
    proc = subprocess.Popen([sys.executable, "-c", stub_code, str(GUI / "server.py"), "--port", str(port)])  # looks like ours
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
        r, a = launch("--port", str(port))
        assert r.returncode == 0, r.stderr
        assert a["port"] == port and a["reused"] is False
        assert ping(port)["version"] == server.API_VERSION
        proc.wait(timeout=10)  # the stub was terminated
    finally:
        proc.kill()


SLEEPER = "import time; time.sleep(60)"


@pytest.fixture
def sleepers():
    procs = []
    yield procs
    for p in procs:
        p.kill()
        p.wait()


def _sleeper(sleepers):
    p = subprocess.Popen([sys.executable, "-c", SLEEPER])
    sleepers.append(p)
    return p


def test_unrelated_live_pid_with_silent_port_is_never_killed(env, sleepers):
    port = free_port()
    victim = _sleeper(sleepers)
    js.write_json_atomic(env / "gui" / "server.json",
                         {"pid": victim.pid, "port": port, "token": "x", "version": 1})
    r, a = launch("--port", str(port))
    assert r.returncode == 0, r.stderr
    assert victim.poll() is None and a["reused"] is False
    assert ping(a["port"])["app"] == "edit-mo-to-gui"


def test_foreign_server_on_recorded_port_and_live_pid_kills_nothing(env, sleepers):
    port = free_port()
    victim = _sleeper(sleepers)

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
        js.write_json_atomic(env / "gui" / "server.json",
                             {"pid": victim.pid, "port": port, "token": "x", "version": 1})
        r, a = launch("--port", str(port))
        assert r.returncode == 0, r.stderr
        assert victim.poll() is None and a["port"] == port + 1
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as resp:
            assert resp.read() == b"hello"  # the foreign server is untouched
    finally:
        srv.shutdown()
        srv.server_close()


def test_dead_pid_in_server_json_starts_fresh(env):
    port = free_port()
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    js.write_json_atomic(env / "gui" / "server.json",
                         {"pid": dead.pid, "port": port, "token": "x", "version": 1})
    r, a = launch("--port", str(port))
    assert r.returncode == 0, r.stderr
    assert a["reused"] is False and a["port"] == port


def test_concurrent_launches_share_one_server(env):
    port = free_port()
    procs = [subprocess.Popen([sys.executable, str(LAUNCH), "--port", str(port)], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True, encoding="utf-8") for _ in range(2)]
    outs = [p.communicate(timeout=60) for p in procs]
    assert [p.returncode for p in procs] == [0, 0], outs
    lines = [json.loads(o[0].strip().splitlines()[-1]) for o in outs]
    assert lines[0]["url"] == lines[1]["url"]
    assert sorted(x["reused"] for x in lines) == [False, True]
    assert ping(port)["app"] == "edit-mo-to-gui"
    for p in range(port + 1, port + 12):  # no second server anywhere: those ports are still bindable
        with socket.socket() as s:
            s.bind(("127.0.0.1", p))


def test_all_ports_busy_is_a_json_error(env):
    port = free_port()
    socks = []
    try:
        for p in range(port, port + 11):
            s = socket.socket()
            s.bind(("127.0.0.1", p))
            s.listen()
            socks.append(s)
        r, a = launch("--port", str(port))
    finally:
        for s in socks:
            s.close()
    assert r.returncode == 1 and a["ok"] is False and "error" in a
    assert "Traceback" not in r.stderr


def test_bad_gui_port_is_a_json_error(env, monkeypatch, capsys):
    import launch as launch_mod
    monkeypatch.setitem(launch_mod.machine.PATHS, "gui_port", "abc")
    with pytest.raises(SystemExit) as e:
        launch_mod.main([])
    assert e.value.code == 1
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["ok"] is False and "error" in out


def test_start_waits_for_server_json_after_child_exits_zero(env, monkeypatch):
    import launch as launch_mod
    import server as server_mod
    port = free_port()
    srv = server_mod.make_server(port, env, env, "tok")
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    holder = subprocess.Popen([sys.executable, "-c", SLEEPER])  # the pid the fixture will kill, never ours

    class Child:  # exits 0 at once ("already running"); the real server's server.json shows up later
        def poll(self):
            return 0

    def fake_popen(*a, **k):
        threading.Timer(0.5, lambda: js.write_json_atomic(
            env / "gui" / "server.json", {"pid": holder.pid, "port": port, "token": "tok", "version": 1})).start()
        return Child()

    import types
    fake = types.SimpleNamespace(**{k: getattr(subprocess, k) for k in dir(subprocess) if not k.startswith("__")})
    fake.Popen = fake_popen
    monkeypatch.setattr(launch_mod, "subprocess", fake)
    try:
        info = launch_mod._start(port, env, env)
    finally:
        srv.shutdown()
        srv.server_close()
        holder.kill()
        holder.wait()
    assert info and info["port"] == port and info["token"] == "tok"


def test_stale_lock_taken_over_by_exactly_one(env):
    import launch as launch_mod
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    lock_path = env / "gui" / "launch.lock"
    js.write_json_atomic(lock_path, {"pid": dead.pid, "time": time.time()})
    barrier = threading.Barrier(2)
    state = {"active": 0, "max": 0, "entered": 0}
    guard = threading.Lock()
    errors = []

    def worker():
        try:
            barrier.wait()
            with launch_mod._Lock(env):
                with guard:
                    state["active"] += 1
                    state["entered"] += 1
                    state["max"] = max(state["max"], state["active"])
                time.sleep(0.3)
                with guard:
                    state["active"] -= 1
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert not errors and state["entered"] == 2 and state["max"] == 1
    assert not lock_path.exists() and not list((env / "gui").glob("launch.lock.*"))


def test_unwritable_tmp_is_a_json_error(env, tmp_path, monkeypatch, capsys):
    import launch as launch_mod
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setenv("EDIT_MO_TO_GUI_TMP", str(blocker))  # a file where the folder should be
    with pytest.raises(SystemExit) as e:
        launch_mod.main(["--port", str(free_port())])
    assert e.value.code == 1
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["ok"] is False


def _wait_dead(pid, seconds=10):
    deadline = time.time() + seconds
    while time.time() < deadline and js.pid_alive(pid):
        time.sleep(0.1)
    return not js.pid_alive(pid)


def test_older_code_version_restarts(env):
    """Our own server reporting another code version (an update was pulled) is replaced, on the same port."""
    port = free_port()
    stub_code = (
        "import json, os\nfrom http.server import BaseHTTPRequestHandler, HTTPServer\n"
        "class H(BaseHTTPRequestHandler):\n"
        "    def do_GET(self):\n"
        "        b = json.dumps({'app': 'edit-mo-to-gui', 'version': 'oldcode', 'pid': os.getpid()}).encode()\n"
        "        self.send_response(200); self.send_header('Content-Length', str(len(b)))\n"
        "        self.end_headers(); self.wfile.write(b)\n"
        "    def log_message(self, *a): pass\n"
        f"HTTPServer(('127.0.0.1', {port}), H).serve_forever()\n")
    proc = subprocess.Popen([sys.executable, "-c", stub_code, str(GUI / "server.py"), "--port", str(port)])  # looks like ours
    try:
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                if ping(port)["version"] == "oldcode":
                    break
            except OSError:
                time.sleep(0.1)
        js.write_json_atomic(env / "gui" / "server.json",
                             {"pid": proc.pid, "port": port, "token": "old", "version": "oldcode"})
        r, a = launch("--port", str(port))
        assert r.returncode == 0, r.stderr
        assert a["port"] == port and a["reused"] is False
        assert ping(port)["version"] == server.API_VERSION
        proc.wait(timeout=10)
    finally:
        proc.kill()


def test_changed_root_restarts(env, tmp_path, monkeypatch):
    """Settings changed root: the next launch replaces our running server (it would refuse the new folders)."""
    port = free_port()
    (tmp_path / "r1").mkdir()
    (tmp_path / "r2").mkdir()
    monkeypatch.setenv("EDIT_MO_TO_GUI_ROOT", str(tmp_path / "r1"))
    r1, a = launch("--port", str(port))
    assert r1.returncode == 0, r1.stderr
    old_pid = info_pid(env)
    assert launch("--port", str(port))[1]["reused"] is True
    monkeypatch.setenv("EDIT_MO_TO_GUI_ROOT", str(tmp_path / "r2"))
    r2, b = launch("--port", str(port))
    assert r2.returncode == 0, r2.stderr
    assert b["reused"] is False and b["port"] == port and b["url"] != a["url"]
    assert _wait_dead(old_pid)
    assert ping(port)["config"] == server.fingerprint(tmp_path / "r2", env)


def test_changed_tmp_never_leaves_two_servers(env, tmp_path, monkeypatch):
    """Settings changed tmp: server.json moves with it, but the old server still holds the port and the same root.
    The launch stops it instead of starting a second server that writes the same inboxes."""
    port = free_port()
    r1, a = launch("--port", str(port))
    assert r1.returncode == 0, r1.stderr
    old_pid = info_pid(env)
    tmp2 = tmp_path / "tmp2"
    tmp2.mkdir()
    monkeypatch.setenv("EDIT_MO_TO_GUI_TMP", str(tmp2))
    try:
        r2, b = launch("--port", str(port))
        assert r2.returncode == 0, r2.stderr
        assert b["reused"] is False and b["port"] == port
        assert _wait_dead(old_pid)
        for p in range(port + 1, port + 12):  # no second server anywhere in the range
            with socket.socket() as s:
                s.bind(("127.0.0.1", p))
    finally:
        pid = info_pid(tmp2)
        if pid:
            kill(pid)


def test_changed_port_moves_the_server(env):
    """Settings changed gui_port: our server outside the new port range is stopped, the new one starts there."""
    port = free_port()
    r1, a = launch("--port", str(port))
    old_pid = info_pid(env)
    other = free_port()
    r2, b = launch("--port", str(other))
    assert r2.returncode == 0, r2.stderr
    assert b["reused"] is False and b["port"] == other
    assert _wait_dead(old_pid)


def _fake_ping_server(port, pid):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            b = json.dumps({"app": "edit-mo-to-gui", "version": "x", "pid": pid}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_impersonating_ping_never_gets_a_pid_killed(env, sleepers):
    """A program answering our ping with someone else's pid is not our server.py: nothing is killed, the port skipped."""
    port = free_port()
    victim = _sleeper(sleepers)
    srv = _fake_ping_server(port, victim.pid)
    try:
        r, a = launch("--port", str(port))
        assert r.returncode == 0, r.stderr
        assert victim.poll() is None and a["port"] == port + 1 and a["reused"] is False
    finally:
        srv.shutdown()
        srv.server_close()


def test_server_json_pid_must_match_the_ping(env, sleepers):
    """server.json names a live pid and the port answers as ours, but with another pid: kill nothing."""
    port = free_port()
    victim = _sleeper(sleepers)
    srv = _fake_ping_server(port, victim.pid + 100000)
    try:
        js.write_json_atomic(env / "gui" / "server.json", {"pid": victim.pid, "port": port, "token": "x", "version": "x"})
        r, a = launch("--port", str(port))
        assert r.returncode == 0, r.stderr
        assert victim.poll() is None and a["port"] == port + 1
    finally:
        srv.shutdown()
        srv.server_close()


@pytest.mark.parametrize("bad", [-1, 0, 1, True, "123", None])
def test_bad_pids_are_never_signalled(env, monkeypatch, bad):
    import launch as launch_mod
    port = free_port()
    killed = []
    monkeypatch.setattr(launch_mod, "_terminate", lambda pid: killed.append(pid) or "")
    monkeypatch.setattr(launch_mod.os, "kill", lambda *a: killed.append(a))
    monkeypatch.setattr(launch_mod, "_start", lambda p, t, r=None: {"pid": 1, "port": p, "token": "t"})
    srv = _fake_ping_server(port, bad)
    try:
        info, reused = launch_mod._launch(port, env, env)
    finally:
        srv.shutdown()
        srv.server_close()
    assert killed == [] and info["port"] == port + 1
    assert launch_mod._is_our_server(bad, port) is False


def test_own_pid_is_never_ours():
    import launch as launch_mod
    assert launch_mod._is_our_server(os.getpid(), 4810) is False


def test_is_our_server_reads_the_command_line(sleepers):
    import launch as launch_mod
    port = free_port()
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", str(GUI / "server.py"), "--port", str(port)])
    sleepers.append(p)
    time.sleep(0.3)
    assert launch_mod._is_our_server(p.pid, port) is True
    assert launch_mod._is_our_server(p.pid, port + 1) is False  # another port
    other = _sleeper(sleepers)
    assert launch_mod._is_our_server(other.pid, port) is False  # not server.py
