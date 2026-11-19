"""The Edit Mo To app's off switch (.claude/edit-mo-to/app.json)."""
import json
import subprocess
import sys
from pathlib import Path

EMT = Path(__file__).resolve().parents[2]          # .claude/edit-mo-to
ROOT = EMT.parents[1]
sys.path.insert(0, str(EMT / "gui"))
import launch as launch_mod  # noqa: E402


def test_app_is_off_in_the_repo():
    assert json.loads((EMT / "app.json").read_text(encoding="utf-8")) == {"enabled": False}
    assert launch_mod.app_enabled() is False


def test_app_enabled_reads_the_file(tmp_path):
    f = tmp_path / "app.json"
    assert launch_mod.app_enabled(f) is True                      # no file: on (older installs)
    f.write_text('{"enabled": true}', encoding="utf-8")
    assert launch_mod.app_enabled(f) is True
    f.write_text('{"enabled": false}', encoding="utf-8")
    assert launch_mod.app_enabled(f) is False
    f.write_text("not json", encoding="utf-8")
    assert launch_mod.app_enabled(f) is False                     # broken file: stay off


def test_launch_refuses_while_off(monkeypatch):
    monkeypatch.delenv("EDIT_MO_TO_APP_SWITCH", raising=False)
    r = subprocess.run([sys.executable, str(EMT / "gui" / "launch.py"), "--open"], capture_output=True, text=True)
    assert r.returncode == 1
    out = json.loads(r.stdout)
    assert out["ok"] is False and out.get("disabled") is True and "turned off" in out["error"]


def test_app_commands_hidden():
    for name in ("edit-mo-to-app", "practice-muna-app"):
        head = (ROOT / ".claude" / "skills" / name / "SKILL.md").read_text(encoding="utf-8").split("---")[1]
        assert "user-invocable: false" in head, name
