import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import update as up


def _runner(changed=(), pull_rc=0, pip_rc=0, npm_rc=0, same=False):
    calls = []

    def run(cmd, cwd=None):
        calls.append(cmd)
        rc, out = 0, ""
        if "rev-parse" in cmd:
            out = "aaa\n" if same or sum("rev-parse" in c for c in calls) == 1 else "bbb\n"
        elif "pull" in cmd:
            rc = pull_rc
        elif "log" in cmd:
            out = "bbb new thing\n"
        elif "diff" in cmd:
            out = "\n".join(changed)
        elif "pip" in cmd:
            rc = pip_rc
        elif cmd[-1] == "ci":
            rc = npm_rc
        return subprocess.CompletedProcess(cmd, rc, out, "boom" if rc else "")
    return run, calls


def test_pull_then_always_install_python_packages():
    run, calls = _runner(changed=["README.md"])
    res = up.update(Path("/r"), run=run, python="py")
    assert res["ok"] and res["pulled"] == 1 and res["python_packages"] == "ok" and res["hyperframes"] == "unchanged"
    pip = next(c for c in calls if "pip" in c)
    assert pip[:4] == ["py", "-m", "pip", "install"] and pip[-1].endswith("requirements.txt")


def test_packages_install_even_when_nothing_new_was_pulled():
    run, calls = _runner(same=True)
    res = up.update(Path("/r"), run=run, python="py")
    assert res["pulled"] == 0 and any("pip" in c for c in calls)


def test_hyperframes_reinstalled_only_when_its_lockfile_changed():
    run, calls = _runner(changed=[".claude/edit-mo-to/motion/package-lock.json"])
    res = up.update(Path("/r"), run=run, python="py")
    assert res["hyperframes"] == "ok (npm ci)" and any(c[-1] == "ci" for c in calls)


def test_a_refused_pull_stops_before_installing():
    run, calls = _runner(pull_rc=1)
    res = up.update(Path("/r"), run=run, python="py")
    assert not res["ok"] and res["step"] == "git pull" and not any("pip" in c for c in calls)


def test_a_failed_pip_is_reported():
    run, _ = _runner(pip_rc=1)
    res = up.update(Path("/r"), run=run, python="py")
    assert not res["ok"] and res["python_packages"].startswith("failed")
