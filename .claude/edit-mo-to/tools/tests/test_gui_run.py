import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
RUN = ROOT / ".claude" / "edit-mo-to" / "run"
SH = shutil.which("sh")

pytestmark = pytest.mark.skipif(SH is None, reason="needs sh")


def _run(*args, cwd=ROOT, run=RUN):
    return subprocess.run([SH, str(run), *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")


def test_run_executes_tool_with_args():
    r = _run("tools/machine.py")
    assert r.returncode == 0, r.stderr
    assert "root" in json.loads(r.stdout)


@pytest.mark.parametrize("script", ["../x.py", "tools/../../x.py", "gui/a b.py", "other/x.py", "tools/x.sh"])
def test_run_refuses_outside_scripts(script):
    r = _run(script)
    assert r.returncode == 2
    assert "refused" in r.stderr


def test_run_passes_args():
    r = _run("tools/media_timing.py", "--help")
    # media_timing prints its docstring via SystemExit (exit 1) for --help: seeing it proves the args arrived
    assert "Voiceover line timings" in r.stdout + r.stderr


def test_run_works_from_a_root_with_spaces(tmp_path):
    root = tmp_path / "Video Editing"
    em = root / ".claude" / "edit-mo-to"
    (em / "tools").mkdir(parents=True)
    shutil.copy(RUN, em / "run")
    (em / "tools" / "echo_args.py").write_text("import sys\nprint(sys.argv[1])\n", encoding="utf-8")
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(em / "tools" / ".venv")], check=True)
    r = _run("tools/echo_args.py", "Uvola Cereza Ácida", cwd=root, run=em / "run")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "Uvola Cereza Ácida"
