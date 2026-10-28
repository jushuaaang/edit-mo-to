"""Task B3: the project status line (gui/statusline.py) prints a short line and saves the plan's usage numbers.

Claude Code pipes its status JSON on stdin (https://code.claude.com/docs/en/statusline). The script must be fast and
never fail the status line: any input prints something and exits 0. It saves only the rate-limit windows that are
present, with the time, to {tmp}/gui/usage.json (atomic write); with no windows it leaves the last reading alone.
"""
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

GUI = Path(__file__).resolve().parents[2] / "gui"
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(GUI))
import statusline  # noqa: E402

RESET_WEEK = 1738857600   # epoch seconds, as Claude Code sends them
RESET_5H = 1738425600
FULL = {"model": {"display_name": "Opus"}, "context_window": {"used_percentage": 12.4},
        "rate_limits": {"five_hour": {"used_percentage": 23.5, "resets_at": RESET_5H},
                        "seven_day": {"used_percentage": 41.2, "resets_at": RESET_WEEK}}}


@pytest.fixture
def gui(tmp_path, monkeypatch):
    monkeypatch.setenv("EDIT_MO_TO_GUI_TMP", str(tmp_path / "t"))   # subprocesses inherit it
    return tmp_path / "t" / "gui"


def run(stdin: "str | bytes", cmd=None):
    data = stdin.encode("utf-8") if isinstance(stdin, str) else stdin
    p = subprocess.run(cmd or [sys.executable, str(GUI / "statusline.py")], input=data, capture_output=True,
                       timeout=20, cwd=ROOT)
    return p.returncode, p.stdout.decode("utf-8"), p.stderr.decode("utf-8")


def test_line_with_both_windows():
    when = datetime.fromtimestamp(RESET_WEEK).astimezone()
    line = statusline.line(FULL)
    assert line.startswith("Week 41% · Now 24% · resets "), line   # rounded, like the app
    assert when.strftime("%a") in line


def test_line_without_rate_limits_shows_model_and_context():
    assert statusline.line({"model": {"display_name": "Opus"}, "context_window": {"used_percentage": 12.4}}) \
        == "Opus · context 12%"
    assert statusline.line({"model": {"display_name": "Sonnet"}}) == "Sonnet"
    assert statusline.line({}) == "edit-mo-to"


def test_partial_windows():
    week_only = {"rate_limits": {"seven_day": {"used_percentage": 5, "resets_at": RESET_WEEK}}}
    assert statusline.line(week_only).startswith("Week 5% · resets ")
    now_only = {"model": {"display_name": "Opus"}, "rate_limits": {"five_hour": {"used_percentage": 80}}}
    assert statusline.line(now_only) == "Now 80%"
    assert statusline.windows(now_only) == {"five_hour": {"used_percentage": 80, "resets_at": None}}
    bad = {"rate_limits": {"seven_day": {"used_percentage": "lots"}, "five_hour": {"used_percentage": 150},
                           "spend_limit": {"used_percentage": 9}}}
    assert statusline.windows(bad) == {}                       # not numbers, out of range, not a plan window


def test_saves_numbers_with_the_time(gui):
    code, out, err = run(json.dumps(FULL))
    assert code == 0 and out.startswith("Week 41% · Now 24%"), (out, err)
    saved = json.loads((gui / "usage.json").read_text(encoding="utf-8"))
    assert set(saved) == {"at", "seven_day", "five_hour"}
    assert saved["seven_day"] == {"used_percentage": 41.2, "resets_at": RESET_WEEK}
    assert saved["five_hour"] == {"used_percentage": 23.5, "resets_at": RESET_5H}
    assert abs(datetime.fromisoformat(saved["at"]).timestamp() - time.time()) < 60
    assert "Opus" not in json.dumps(saved)                     # numbers and times only
    assert not [p for p in gui.iterdir() if p.name.endswith(".tmp")]


def test_partial_window_saved_alone_and_no_window_keeps_the_last_reading(gui):
    run(json.dumps({"rate_limits": {"seven_day": {"used_percentage": 7, "resets_at": RESET_WEEK}}}))
    saved = json.loads((gui / "usage.json").read_text(encoding="utf-8"))
    assert set(saved) == {"at", "seven_day"}
    code, out, _ = run(json.dumps({"model": {"display_name": "Opus"}}))   # before the session's first reply
    assert code == 0 and out.strip() == "Opus"
    assert json.loads((gui / "usage.json").read_text(encoding="utf-8")) == saved


@pytest.mark.parametrize("junk", [b"", b"not json", b"[1,2]", b"\xff\xfe\x00", b'{"rate_limits": 5}',
                                  b'{"rate_limits": {"seven_day": [1]}, "model": "x"}'])
def test_garbage_still_prints_and_exits_0(gui, junk):
    code, out, err = run(junk)
    assert code == 0 and out.strip(), (out, err)
    assert not (gui / "usage.json").exists()


def test_unwritable_tmp_still_prints(tmp_path, monkeypatch):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("EDIT_MO_TO_GUI_TMP", str(blocker))     # gui dir can't be made under a file
    code, out, _ = run(json.dumps(FULL))
    assert code == 0 and out.startswith("Week 41%")


def test_fast_and_light(gui):
    start = time.monotonic()
    run(json.dumps(FULL))
    assert time.monotonic() - start < 2.0
    src = (GUI / "statusline.py").read_text(encoding="utf-8")
    for heavy in ("urllib", "requests", "socket", "subprocess", "http"):
        assert f"import {heavy}" not in src, heavy


def test_runs_through_the_run_launcher(gui):
    run_sh = ROOT / ".claude" / "edit-mo-to" / "run"
    code, out, err = run(json.dumps(FULL), cmd=[str(run_sh), "gui/statusline.py"])
    assert code == 0 and out.startswith("Week 41%"), err
    assert (gui / "usage.json").exists()


def test_settings_json_has_the_status_line_and_keeps_the_allow_rule():
    s = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert s["statusLine"] == {"type": "command", "command": ".claude/edit-mo-to/run gui/statusline.py"}
    assert "Bash(.claude/edit-mo-to/run *)" in s["permissions"]["allow"]


def test_readme_says_the_status_line_is_for_the_video_folder_only():
    r = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "gui/statusline.py" in r and "status line" in r
    assert "only inside your Video Editing folder" in r
