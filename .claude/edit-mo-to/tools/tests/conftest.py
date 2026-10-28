"""Shared test isolation (Task G fix): GUI tests never read this computer's real ~/.claude.json or machine.json.

For every GUI test module (test_gui_*.py, test_generate_for_me.py) an autouse fixture
  - points HOME and USERPROFILE at an empty temp folder (subprocesses inherit it),
  - clears CLAUDE_CONFIG_DIR (Claude Code's config folder override, which gui/usage.py follows),
  - points machine.CONFIG at a temp machine.json ({} : "Generate for me" off),
  - clears account._cache, and
  - makes account._home refuse the real home folder, so a read of the real ~/.claude.json fails the test.
A test that needs the switch or an account writes its own files (test_generate_for_me.py does).
"""
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
GUI = TOOLS.parent / "gui"
for _p in (str(GUI), str(TOOLS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import account  # noqa: E402
import machine  # noqa: E402

REAL_HOME = Path.home().resolve()
REAL_CONFIG = Path(machine.CONFIG).resolve()
_real_home_fn = account._home


def _is_gui_test(request) -> bool:
    name = request.module.__name__.rsplit(".", 1)[-1]
    return name.startswith("test_gui_") or name == "test_generate_for_me"


def _guarded_home(home=None):
    got = _real_home_fn(home)
    if got.resolve() == REAL_HOME:
        raise AssertionError("a test tried to read the real ~/.claude.json")
    return got


@pytest.fixture(autouse=True)
def _no_real_home(request, tmp_path_factory, monkeypatch):
    if not _is_gui_test(request):
        yield
        return
    base = tmp_path_factory.mktemp("isolated")
    home = base / "home"
    home.mkdir()
    cfg = base / "machine.json"
    cfg.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)   # usage.claude_dir() follows it: never the real one
    monkeypatch.setattr(machine, "CONFIG", cfg)
    monkeypatch.setattr(account, "_home", _guarded_home)
    account._cache.clear()
    yield {"home": home, "config": cfg}
    account._cache.clear()
