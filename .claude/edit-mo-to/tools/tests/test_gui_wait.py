import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

GUI = Path(__file__).resolve().parents[2] / "gui"
sys.path.insert(0, str(GUI))
import jobstate as js  # noqa: E402

WAIT = GUI / "wait.py"
_procs: list = []


def _kill_tree(p):
    # the venv python on Windows is a launcher: p.pid is the launcher, the waiter its child
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
    elif p.poll() is None:
        p.kill()


def _kill_real(folder):
    """Kill whatever pid listening.json names (the real waiter, even if its launcher is gone)."""
    try:
        pid = int(json.loads((js.state_dir(folder) / "listening.json").read_text(encoding="utf-8"))["pid"])
    except (OSError, ValueError, KeyError):
        return
    if pid != os.getpid() and js.pid_alive(pid):
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
        else:
            os.kill(pid, signal.SIGKILL)


@pytest.fixture(autouse=True)
def _reap():
    yield
    for p, folder in _procs:
        _kill_tree(p)  # on Windows even if the launcher already exited
        _kill_real(folder)
        p.wait()
        for s in (p.stdout, p.stderr):
            if s:
                s.close()
    _procs.clear()


def _start(folder, *args, step="storyboard", **popen):
    cmd = [sys.executable, str(WAIT), str(folder), "--after", "0", "--step", step, "--poll", "0.1", *args]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **popen)
    _procs.append((p, folder))
    return p


def _until(cond, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def _out(p, timeout=10):
    out, err = p.communicate(timeout=timeout)
    assert err == b"", err.decode("utf-8", "replace")
    return json.loads(out.decode("utf-8").strip().splitlines()[-1])


def test_returns_existing_unread_event_immediately(tmp_path):
    js.append_event(tmp_path, {"type": "message", "text": "hi"})
    t = time.time()
    p = _start(tmp_path, "--timeout", "5")
    out = _out(p)
    assert p.returncode == 0
    assert time.time() - t < 2 + 3  # interpreter start slack
    assert [e["seq"] for e in out["events"]] == [1]
    assert js.listening(tmp_path) is None


def test_wakes_on_new_event(tmp_path):
    p = _start(tmp_path, "--timeout", "10")
    assert _until(lambda: js.listening(tmp_path) is not None)
    js.append_event(tmp_path, {"type": "answer", "text": "ok"})
    out = _out(p)
    assert p.returncode == 0
    assert out["events"][0]["text"] == "ok"
    assert not (js.state_dir(tmp_path) / "listening.json").exists()


def test_timeout_exit_code(tmp_path):
    p = _start(tmp_path, "--timeout", "1")
    assert _out(p) == {"events": []}
    assert p.returncode == 3
    assert js.listening(tmp_path) is None


def test_listening_visible_while_waiting(tmp_path):
    p = _start(tmp_path, "--timeout", "10")
    assert _until(lambda: js.listening(tmp_path) is not None)
    info = js.listening(tmp_path)
    assert info["step"] == "storyboard" and js.pid_alive(info["pid"])
    first = info["beat"]
    assert _until(lambda: (js.listening(tmp_path) or {}).get("beat", first) > first)


def test_second_waiter_takes_over(tmp_path):
    a = _start(tmp_path, "--timeout", "20")
    assert _until(lambda: js.listening(tmp_path) is not None)
    a_pid = js.listening(tmp_path)["pid"]
    b = _start(tmp_path, "--timeout", "20")
    assert _until(lambda: a.poll() is not None)
    assert a.returncode == 4
    assert json.loads(a.stdout.read().decode().strip()) == {"superseded": True}
    assert _until(lambda: (js.listening(tmp_path) or {}).get("pid") not in (None, a_pid))
    assert b.poll() is None


def test_folder_with_spaces_and_accents(tmp_path):
    folder = tmp_path / "Café vidéo"
    folder.mkdir()
    js.append_event(folder, {"type": "message", "text": "ñandú ✓"})
    out = _out(_start(folder, "--timeout", "5"))
    assert out["events"][0]["text"] == "ñandú ✓"


def test_missing_inbox_times_out(tmp_path):
    assert not js.state_dir(tmp_path).exists()
    p = _start(tmp_path, "--timeout", "1")
    assert _out(p) == {"events": []}
    assert p.returncode == 3


def test_superseded_waiter_leaves_new_file_intact(tmp_path):
    a = _start(tmp_path, "--timeout", "20")
    assert _until(lambda: js.listening(tmp_path) is not None)
    a_pid = js.listening(tmp_path)["pid"]
    b = _start(tmp_path, "--timeout", "20")
    assert _until(lambda: a.poll() is not None)
    assert a.returncode == 4
    path = js.state_dir(tmp_path) / "listening.json"
    first = json.loads(path.read_text(encoding="utf-8"))
    assert first["pid"] != a_pid  # b took over and a did not overwrite it
    time.sleep(0.5)
    later = json.loads(path.read_text(encoding="utf-8"))
    assert later["pid"] == first["pid"] and later["since"] == first["since"]
    assert js.pid_alive(later["pid"]) and b.poll() is None


def test_terminate_clears_listening_and_exits_130(tmp_path):
    if sys.platform == "win32":
        pytest.skip("terminate() is a hard kill on Windows; see the CTRL_BREAK test")
    p = _start(tmp_path, "--timeout", "30")
    assert _until(lambda: js.listening(tmp_path) is not None)
    p.terminate()
    p.wait(timeout=10)
    assert p.returncode == 130
    assert not (js.state_dir(tmp_path) / "listening.json").exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows console break")
def test_ctrl_break_clears_listening_and_exits_130(tmp_path):
    p = _start(tmp_path, "--timeout", "30", creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    assert _until(lambda: js.listening(tmp_path) is not None)
    real = js.listening(tmp_path)["pid"]
    os.kill(p.pid, signal.CTRL_BREAK_EVENT)
    p.wait(timeout=10)
    assert _until(lambda: not js.pid_alive(real))
    assert not (js.state_dir(tmp_path) / "listening.json").exists()
    assert p.returncode == 130


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX reparenting")
def test_orphaned_waiter_exits(tmp_path):
    """Claude Code gone (the shell that started wait.py died): the waiter stops, so the GUI never shows a false
    "Claude is listening"."""
    folder = tmp_path / "vid"
    js.save(folder, js.new_job(folder, "A", "B"))
    out = tmp_path / "w.out"
    sh = subprocess.run(["sh", "-c", f'"{sys.executable}" "{WAIT}" "{folder}" --poll 0.1 > "{out}" 2>&1 & echo $!; sleep 1.5'],
                        capture_output=True, text=True, timeout=10)
    pid = int(sh.stdout.strip())
    try:
        deadline = time.time() + 5
        while time.time() < deadline and js.listening(folder) is None:
            time.sleep(0.1)
        deadline = time.time() + 5
        while time.time() < deadline and js.pid_alive(pid):
            time.sleep(0.1)
        assert not js.pid_alive(pid), "the orphaned wait.py kept running"
        assert js.listening(folder) is None
    finally:
        if js.pid_alive(pid):
            os.kill(pid, signal.SIGKILL)
