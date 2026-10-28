"""Task B3: plan usage as a percentage, videos left, and token details (gui/usage.py, job.py usage-mark, /api/usage).

Every test uses temp folders: a fake HOME (conftest) with fake Claude logs, a temp {tmp}; never the real ~/.claude.
"""
import json
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

GUI = Path(__file__).resolve().parents[2] / "gui"
STATIC = GUI / "static"
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(GUI))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jobstate as js  # noqa: E402
import server  # noqa: E402
import usage  # noqa: E402

JOB = GUI / "job.py"
TOKEN = "tok-b3"
SECRET = "SECRET conversation text"
NOW = datetime(2026, 10, 28, 15, 0, tzinfo=timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def msg(at: datetime, mid: str, inp=10, cw=100, cr=1000, out=5) -> dict:
    return {"type": "assistant", "timestamp": iso(at), "sessionId": "s",
            "message": {"id": mid, "role": "assistant", "content": [{"type": "text", "text": SECRET}],
                        "usage": {"input_tokens": inp, "cache_creation_input_tokens": cw,
                                  "cache_read_input_tokens": cr, "output_tokens": out}}}


def write_log(path: Path, lines: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for line in lines:
            f.write((line if isinstance(line, str) else json.dumps(line)) + "\n")


@pytest.fixture
def home(_no_real_home):
    return _no_real_home["home"]


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "Video Editing.v2"
    r.mkdir()
    return r


@pytest.fixture
def logs(home, root):
    """Two sessions, a helper (subagent) log in a subfolder, a line without usage, a garbage line, a split message."""
    usage._cache.clear()
    d = home / ".claude" / "projects" / usage.project_log_name(root)
    write_log(d / "s1.jsonl", [
        {"type": "user", "timestamp": iso(NOW - timedelta(hours=3)), "message": {"role": "user", "content": SECRET}},
        msg(NOW - timedelta(hours=3), "m1"),                 # 1115
        msg(NOW - timedelta(hours=3), "m1"),                 # the same reply, another content block: counted once
        "{not json",
        msg(NOW - timedelta(hours=2), "m2", inp=1, cw=0, cr=0, out=1),   # 2
    ])
    write_log(d / "s2.jsonl", [msg(NOW - timedelta(days=2), "m3", inp=0, cw=0, cr=0, out=100)])   # 100, two days ago
    write_log(d / "s1" / "subagents" / "agent-a.jsonl", [msg(NOW - timedelta(hours=1), "h1", 0, 0, 0, 50)])  # helper
    write_log(d / "s1" / "tool-results" / "x.txt", ["not a log"])
    return d


# ---------- the project log folder ----------

def test_project_log_name_like_claude_code():
    assert usage.project_log_name("/Users/joshuacalonge/Video Editing") == "-Users-joshuacalonge-Video-Editing"
    assert usage.project_log_name("/a/b.c d") == "-a-b-c-d"
    assert usage.project_log_name("C:\\Users\\x\\Video Editing") == "C--Users-x-Video-Editing"


def test_project_logs_found_or_none(home, root):
    assert usage.project_logs(root) is None
    d = home / ".claude" / "projects" / usage.project_log_name(root)
    d.mkdir(parents=True)
    assert usage.project_logs(root) == d


def test_claude_config_dir_is_followed(tmp_path, root, monkeypatch):
    cfg = tmp_path / "cfg"
    (cfg / "projects" / usage.project_log_name(root)).mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(cfg))
    assert usage.project_logs(root) == cfg / "projects" / usage.project_log_name(root)


# ---------- token sums from the logs ----------

def test_tokens_summed_only_numbers(logs):
    entries = usage.entries(logs)
    assert all(set(e) == {"t", "id", "in", "cw", "cr", "out", "helper"} for e in entries)
    assert SECRET not in json.dumps(entries)
    day = usage.tokens(entries, (NOW - timedelta(hours=5)).timestamp(), NOW.timestamp())
    assert day == {"total": 1167, "claude": 1117, "helpers": 50, "input": 11, "cache_write": 100,
                   "cache_read": 1000, "output": 56}
    week = usage.tokens(entries, (NOW - timedelta(days=7)).timestamp(), NOW.timestamp())
    assert week["total"] == 1267


def test_entries_cached_by_size_and_mtime_and_read_on_growth(logs):
    first = usage.entries(logs)
    assert usage.entries(logs) == first
    calls = []
    real = usage._parse_lines
    usage._parse_lines = lambda *a, **k: calls.append(1) or real(*a, **k)
    try:
        usage.entries(logs)
        assert calls == []                                    # nothing changed: nothing read again
        write_log(logs / "s2.jsonl", [msg(NOW, "m4", 0, 0, 0, 7)])
        got = usage.entries(logs)
        assert len(calls) == 1 and len(got) == len(first) + 1
    finally:
        usage._parse_lines = real


# ---------- the status line reading ----------

def write_auto(gui: Path, week=40.0, five=20.0, at=None, resets=None):
    gui.mkdir(parents=True, exist_ok=True)
    at = at or datetime.now().astimezone()
    data = {"at": at.isoformat(timespec="seconds")}
    if week is not None:
        data["seven_day"] = {"used_percentage": week, "resets_at": resets or int(time.time()) + 3 * 86400}
    if five is not None:
        data["five_hour"] = {"used_percentage": five, "resets_at": int(time.time()) + 3600}
    (gui / "usage.json").write_text(json.dumps(data), encoding="utf-8")
    return data


def test_read_auto_fresh_old_missing_and_reset(tmp_path):
    gui = tmp_path / "gui"
    assert usage.read_auto(gui) is None
    write_auto(gui)
    a = usage.read_auto(gui)
    assert a["week_pct"] == 40.0 and a["five_hour_pct"] == 20.0 and a["old"] is False
    write_auto(gui, at=datetime.now().astimezone() - timedelta(minutes=31))
    assert usage.read_auto(gui)["old"] is True
    write_auto(gui, resets=int(time.time()) - 10)               # the week reset since: that % is gone
    assert usage.read_auto(gui)["week_pct"] is None and usage.read_auto(gui)["old"] is True
    (gui / "usage.json").write_text("garbage", encoding="utf-8")
    assert usage.read_auto(gui) is None


# ---------- percent per video and videos left ----------

def job_with(start, finish, rs=1000, rf=1000):
    return {"usage": {"start_pct": start, "finish_pct": finish, "start_resets_at": rs, "finish_resets_at": rf}}


def test_per_video_pct_needs_three_and_drops_resets():
    two = [job_with(10, 16), job_with(20, 24)]
    assert usage.per_video_pct(two) == (None, 2)
    jobs = two + [job_with(30, 38), job_with(50, 10), job_with(5, 9, rs=1000, rf=900000), {"usage": {"start_pct": 3}}, {}]
    assert usage.per_video_pct(jobs) == (6.0, 3)               # (6 + 4 + 8) / 3; the reset ones are dropped


def test_videos_left_rounds_down_never_below_zero():
    assert usage.videos_left(40, 6) == 10
    assert usage.videos_left(99, 6) == 0
    assert usage.videos_left(120, 6) == 0
    assert usage.videos_left(40, None) is None and usage.videos_left(None, 6) is None
    assert usage.videos_left(40, 0) is None


# ---------- job.py: the week % at start and finish ----------

def run_job(env_tmp, *args):
    import os
    env = {**os.environ, "EDIT_MO_TO_GUI_TMP": str(env_tmp)}
    p = subprocess.run([sys.executable, str(JOB), *map(str, args)], capture_output=True, text=True, encoding="utf-8",
                       env=env)
    out = json.loads(p.stdout.strip().splitlines()[-1])
    assert out["ok"], p.stdout + p.stderr
    return out


def test_init_and_export_done_save_the_week_pct(tmp_path):
    tmp = tmp_path / "t"
    folder = tmp_path / "vid"
    run_job(tmp, "init", folder, "--client", "A", "--product", "B")
    assert "usage" not in js.load(folder)                     # no reading yet: skipped, nothing guessed
    resets = int(time.time()) + 3 * 86400
    write_auto(tmp / "gui", week=30, resets=resets)
    out = run_job(tmp, "usage-mark", folder, "start")
    assert out["usage"]["start_pct"] == 30
    write_auto(tmp / "gui", week=37.5, resets=resets)
    run_job(tmp, "step", folder, "export", "done")
    u = js.load(folder)["usage"]
    assert u["start_pct"] == 30 and u["finish_pct"] == 37.5 and u["start_resets_at"] == u["finish_resets_at"] == resets
    assert u["start_at"] and u["finish_at"]
    assert js.load(folder)["finished"]


def test_init_marks_start_and_old_reading_is_skipped(tmp_path):
    tmp = tmp_path / "t"
    write_auto(tmp / "gui", week=12)
    run_job(tmp, "init", tmp_path / "a", "--client", "A", "--product", "B")
    assert js.load(tmp_path / "a")["usage"]["start_pct"] == 12
    write_auto(tmp / "gui", week=12, at=datetime.now().astimezone() - timedelta(hours=2))
    run_job(tmp, "init", tmp_path / "b", "--client", "A", "--product", "B")
    assert "usage" not in js.load(tmp_path / "b")
    out = run_job(tmp, "usage-mark", tmp_path / "b", "finish")
    assert out["usage"] is None


# ---------- manual fallback ----------

def test_manual_estimate_learns_tokens_per_percent(logs):
    entries = usage.entries(logs)
    r1 = {"pct": 10, "at": (NOW - timedelta(hours=4)).isoformat()}
    r2 = {"pct": 20, "at": (NOW - timedelta(hours=1, minutes=30)).isoformat()}   # 1117 tokens between: ~111.7 per %
    m = usage.manual([r1, r2], entries, NOW.timestamp())
    assert m["last"] == {"pct": 20, "at": r2["at"]}
    assert m["learned"] is True
    assert m["estimate_pct"] == pytest.approx(20 + 50 / 111.7, abs=0.01)   # the helper's 50 tokens after r2
    assert m["old"] is False
    one = usage.manual([r1], entries, NOW.timestamp())
    assert one["learned"] is False and one["estimate_pct"] == 10
    stale = usage.manual([{"pct": 10, "at": (NOW - timedelta(days=2)).isoformat()}], entries, NOW.timestamp())
    assert stale["old"] is True
    assert usage.manual([], entries, NOW.timestamp())["last"] is None


# ---------- /api/usage ----------

class Api:
    def __init__(self, port):
        self.base = f"http://127.0.0.1:{port}"

    def json(self, method, path, body=None, token=TOKEN):
        h = {"X-EMT-Token": token} if token else {}
        data = None if body is None else json.dumps(body).encode("utf-8")
        if body is not None:
            h["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null")


@pytest.fixture
def api(root, tmp_path, monkeypatch):
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    monkeypatch.setenv("EDIT_MO_TO_GUI_TMP", str(tmp))
    srv = server.make_server(0, root, tmp, TOKEN)
    t = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    t.start()
    a = Api(srv.server_address[1])
    a.root, a.tmp = root, tmp
    yield a
    srv.shutdown()
    srv.server_close()


def finished_job(root: Path, name: str, start: float, finish: float, resets: int, created=None):
    folder = root / name
    folder.mkdir()
    job = js.new_job(folder, "C", name)
    now = datetime.now().astimezone()
    job["created"] = (created or now - timedelta(hours=2)).isoformat(timespec="seconds")
    job["steps"]["export"]["state"] = "done"
    job["finished"] = (now - timedelta(hours=1)).isoformat(timespec="seconds")
    job["usage"] = {"start_pct": start, "finish_pct": finish, "start_resets_at": resets, "finish_resets_at": resets,
                    "start_at": job["created"], "finish_at": job["finished"]}
    js.save(folder, job)


def test_api_usage_without_anything_says_so(api, home):
    usage._cache.clear()
    s, d = api.json("GET", "/api/usage")
    assert s == 200
    assert d["auto"] is None and d["stale"] is True and d["tokens"] is None
    assert d["per_video_pct"] is None and d["videos_left"] is None
    assert d["manual"] == {"last": None, "estimate_pct": None, "learned": False, "tokens_per_pct": None, "old": True,
                           "readings": 0}
    assert api.json("GET", "/api/usage", token=None)[0] == 401


def test_api_usage_with_auto_logs_and_three_videos(api, logs):
    resets = int(time.time()) + 3 * 86400
    write_auto(api.tmp / "gui", week=40, five=20, resets=resets)
    for name, a, b in (("V1", 10, 16), ("V2", 20, 24), ("V3", 30, 38)):
        finished_job(api.root, name, a, b, resets)
    s, d = api.json("GET", "/api/usage")
    assert s == 200
    assert d["auto"]["week_pct"] == 40 and d["auto"]["five_hour_pct"] == 20 and d["auto"]["week_resets_at"] == resets
    assert d["stale"] is False and d["manual"] is None
    assert d["per_video_pct"] == 6.0 and d["videos_left"] == 10 and d["videos_counted"] == 3
    assert set(d["tokens"]) == {"today", "week", "per_job"}
    assert {j["name"] for j in d["tokens"]["per_job"]} == {"V1", "V2", "V3"}
    assert all(j["about"] for j in d["tokens"]["per_job"])     # the three overlap in time
    assert SECRET not in json.dumps(d)


def test_api_usage_old_reading_offers_manual_and_saves_readings(api, home):
    usage._cache.clear()
    write_auto(api.tmp / "gui", at=datetime.now().astimezone() - timedelta(hours=1))
    s, d = api.json("GET", "/api/usage")
    assert d["stale"] is True and d["auto"]["old"] is True and d["manual"] is not None
    assert api.json("POST", "/api/usage", {"pct": 140})[0] == 400
    assert api.json("POST", "/api/usage", {"pct": "40"})[0] == 400
    s, d = api.json("POST", "/api/usage", {"pct": 40})
    assert s == 200 and d["manual"]["last"]["pct"] == 40 and d["manual"]["readings"] == 1
    prefs = js.read_prefs(api.tmp / "gui" / "prefs.json")
    assert [r["pct"] for r in prefs["usage_readings"]] == [40]


def test_usage_readings_pref_is_checked():
    js.check_pref("usage_readings", [{"pct": 40, "at": "2026-10-28T10:00:00+08:00"}])
    for bad in ([{"pct": 101, "at": "2026-10-28T10:00:00"}], [{"pct": 4}], "x", [{"pct": 4, "at": "nope"}]):
        with pytest.raises(ValueError):
            js.check_pref("usage_readings", bad)


# ---------- the dashboard box ----------

def test_dashboard_usage_box():
    dash = (STATIC / "pages" / "dashboard.js").read_text(encoding="utf-8")
    for needle in ('"/api/usage"', "usage.update", "usage.update_old", "usage.hint_exact", "usage.open_claude",
                   "usage.details", "usage.not_available", "/usage", "copyButton(", "usage.not_enough",
                   "usage.per_video", "usage.left", "usage.week", "usage.now"):
        assert needle in dash, needle
    words = (STATIC / "words.js").read_text(encoding="utf-8")
    assert '"usage": ["title", "update", "update_old"' in words


def test_readme_and_steps_mention_usage():
    steps = (ROOT / ".claude" / "skills" / "edit-mo-to" / "reference" / "steps.md").read_text(encoding="utf-8")
    assert "usage-mark" in steps


# ---------- fix round 1 ----------

def test_partial_last_line_waits_until_complete(home, root):
    usage._cache.clear()
    d = home / ".claude" / "projects" / usage.project_log_name(root)
    d.mkdir(parents=True)
    log = d / "s.jsonl"
    whole = json.dumps(msg(NOW, "a1", 0, 0, 0, 3)) + "\n"
    half = json.dumps(msg(NOW, "a2", 0, 0, 0, 4))
    log.write_text(whole + half[:40], encoding="utf-8")            # Claude Code is mid-write
    assert [e["id"] for e in usage.entries(d)] == ["a1"]
    with log.open("a", encoding="utf-8") as f:
        f.write(half[40:])                                        # still no newline: still waits
    assert [e["id"] for e in usage.entries(d)] == ["a1"]
    with log.open("a", encoding="utf-8") as f:
        f.write("\n")
    assert [e["id"] for e in usage.entries(d)] == ["a1", "a2"]
    assert usage._cache[str(log)]["offset"] == log.stat().st_size


def test_logs_read_line_by_line_not_whole():
    src = (GUI / "usage.py").read_text(encoding="utf-8")
    assert "f.read()" not in src and ".split(b\"\\n\")" not in src
    assert "for raw in f" in src


def test_manual_mode_estimates_per_video_and_videos_left_from_tokens(api, home):
    """No status line: two typed readings teach tokens per 1%; three finished videos then give "about N%" per video."""
    usage._cache.clear()
    logs = home / ".claude" / "projects" / usage.project_log_name(api.root)   # only this test's lines, on the real clock
    resets = int(time.time()) + 3 * 86400
    now = datetime.now().astimezone()
    for i, name in enumerate(("V1", "V2", "V3")):
        folder = api.root / name
        folder.mkdir()
        job = js.new_job(folder, "C", name)
        job["created"] = (now - timedelta(hours=10 - 3 * i)).isoformat(timespec="seconds")
        job["steps"]["export"]["state"] = "done"
        job["finished"] = (now - timedelta(hours=9 - 3 * i)).isoformat(timespec="seconds")
        js.save(folder, job)
        write_log(logs / f"v{i}.jsonl", [msg(now - timedelta(hours=9.5 - 3 * i), f"v{i}", 0, 0, 0, 1000 * (i + 1))])
    write_log(logs / "r.jsonl", [msg(now - timedelta(minutes=50), "r1", 0, 0, 0, 2000)])   # between the readings
    js.update_prefs(api.tmp / "gui", {"usage_readings": [
        {"pct": 10, "at": (now - timedelta(hours=1)).isoformat(timespec="seconds")},
        {"pct": 20, "at": (now - timedelta(minutes=10)).isoformat(timespec="seconds")}]})    # 2000 tokens = 10%: 200 per 1%
    s, d = api.json("GET", "/api/usage")
    assert d["auto"] is None and d["manual"]["learned"] is True
    assert d["manual"]["tokens_per_pct"] == pytest.approx(200)
    assert d["per_video_pct"] == pytest.approx(10.0)              # (1000 + 2000 + 3000) / 3 / 200
    assert d["per_video_source"] == "tokens" and d["videos_counted"] == 3
    assert d["videos_left"] == 8                                  # floor((100 - 20) / 10)


def test_manual_per_video_needs_three_finished_videos(api, logs):
    now = datetime.now().astimezone()
    js.update_prefs(api.tmp / "gui", {"usage_readings": [
        {"pct": 10, "at": (NOW - timedelta(hours=4)).isoformat()},
        {"pct": 20, "at": (NOW - timedelta(hours=1, minutes=30)).isoformat()}]})
    finished = api.root / "One"
    finished.mkdir()
    job = js.new_job(finished, "C", "One")
    job["steps"]["export"]["state"] = "done"
    job["finished"] = now.isoformat(timespec="seconds")
    js.save(finished, job)
    s, d = api.json("GET", "/api/usage")
    assert d["per_video_pct"] is None and d["videos_left"] is None


def test_week_reading_kept_when_a_reply_has_only_the_five_hour_window(tmp_path, monkeypatch):
    sys.path.insert(0, str(GUI))
    import statusline
    monkeypatch.setenv("EDIT_MO_TO_GUI_TMP", str(tmp_path / "t"))
    gui = tmp_path / "t" / "gui"
    resets = int(time.time()) + 86400
    statusline.save({"rate_limits": {"seven_day": {"used_percentage": 30, "resets_at": resets},
                                     "five_hour": {"used_percentage": 5, "resets_at": resets}}})
    first = json.loads((gui / "usage.json").read_text(encoding="utf-8"))
    statusline.save({"rate_limits": {"five_hour": {"used_percentage": 9, "resets_at": resets}}})
    saved = json.loads((gui / "usage.json").read_text(encoding="utf-8"))
    assert saved["five_hour"]["used_percentage"] == 9
    assert saved["seven_day"]["used_percentage"] == 30
    assert saved["seven_day"]["at"] == first["at"]                 # the week keeps its own time
    a = usage.read_auto(gui)
    assert a["week_pct"] == 30 and a["week_at"] == first["at"]
    # a week reading taken over 30 minutes ago stays old even though the five-hour one is new
    old = (datetime.now().astimezone() - timedelta(minutes=40)).isoformat(timespec="seconds")
    saved["seven_day"]["at"] = old
    (gui / "usage.json").write_text(json.dumps(saved), encoding="utf-8")
    assert usage.read_auto(gui)["old"] is True
    # a past week is not carried over
    saved["seven_day"]["resets_at"] = int(time.time()) - 5
    (gui / "usage.json").write_text(json.dumps(saved), encoding="utf-8")
    statusline.save({"rate_limits": {"five_hour": {"used_percentage": 9, "resets_at": resets}}})
    assert "seven_day" not in json.loads((gui / "usage.json").read_text(encoding="utf-8"))


def test_job_with_a_missing_resets_at_is_left_out():
    jobs = [job_with(10, 16), job_with(20, 24), job_with(30, 38)]
    assert usage.per_video_pct(jobs + [job_with(1, 90, rs=None)]) == (6.0, 3)
    assert usage.per_video_pct(jobs + [job_with(1, 90, rf=None)]) == (6.0, 3)
    assert usage.per_video_pct([job_with(10, 16, rs=None, rf=None)] * 3) == (None, 0)


def test_zero_percent_per_video_is_shown_not_not_enough():
    dash = (STATIC / "pages" / "dashboard.js").read_text(encoding="utf-8")
    assert "u?.per_video_pct ?" not in dash                        # 0 is a real average
    assert "u.per_video_pct !== null" in dash and "usage.per_video_small" in dash
    assert usage.per_video_pct([job_with(10, 10)] * 3) == (0.0, 3)


def test_claude_config_dir_cleared_for_gui_tests():
    import os
    assert "CLAUDE_CONFIG_DIR" not in os.environ
    assert str(usage.claude_dir()).startswith(str(Path.home()))


def test_conftest_clears_claude_config_dir_even_when_the_shell_sets_it(tmp_path):
    import os
    env = {**os.environ, "CLAUDE_CONFIG_DIR": str(tmp_path / "real-looking")}
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", __file__,
                        "-k", "test_claude_config_dir_cleared_for_gui_tests"], capture_output=True, text=True,
                       cwd=Path(__file__).resolve().parents[1], env=env, timeout=120)
    assert p.returncode == 0, p.stdout[-2000:]
