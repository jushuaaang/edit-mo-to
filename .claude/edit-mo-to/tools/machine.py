"""Per-machine paths, so the same repo runs on the Windows PC and the Mac.

Reads ../machine.json (untracked; copy machine.example.json). Any key it leaves out falls back to this
platform's default below.

usage: python machine.py   prints the resolved paths as JSON
"""
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
CONFIG = TOOLS.parent / "machine.json"
ROOT = TOOLS.parents[2]
HOME = Path.home()

if sys.platform == "win32":
    _DEFAULTS = {
        "python": str(TOOLS / ".venv" / "Scripts" / "python.exe"),
        "capcut_drafts": str(HOME / "AppData/Local/CapCut/User Data/Projects/com.lveditor.draft"),
    }
else:
    _DEFAULTS = {
        "python": str(TOOLS / ".venv" / "bin" / "python"),
        "capcut_drafts": str(HOME / "Movies/CapCut/User Data/Projects/com.lveditor.draft"),
    }
_DEFAULTS.update({
    "root": str(ROOT),
    "mcp_servers": str(HOME / "mcp-servers"),
    "tmp": str(HOME / "mcp-servers" / "tmp"),
})


def load() -> dict:
    cfg = dict(_DEFAULTS)
    if CONFIG.exists():
        cfg.update(json.loads(CONFIG.read_text(encoding="utf-8")))
    return cfg


PATHS = load()
TMP = Path(PATHS["tmp"])
BUILD = (TMP / "build").as_posix()

if __name__ == "__main__":
    print(json.dumps(PATHS, indent=1))
