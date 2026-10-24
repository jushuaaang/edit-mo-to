"""Per-machine paths, so the same repo runs on the Windows PC and the Mac.

Reads ../machine.json (untracked; copy machine.example.json). Any key it leaves out falls back to this
platform's default below.

usage: python machine.py   prints the resolved paths as JSON
"""
import json
import os
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
    "asr": "faster-whisper",  # speech backend: "faster-whisper" (CUDA when present) or "mlx" (Apple silicon)
    "asr_device": "auto",  # faster-whisper device: "auto" (CUDA when it works, else CPU), "cpu" or "cuda"
    "render_workers": 1,  # hyperframes --workers per overlay render: 1 skips the ~1.7 s calibration launch
    "render_concurrency": min(4, max(1, (os.cpu_count() or 2) // 2)),  # overlay renders side by side
})


def load() -> dict:
    cfg = dict(_DEFAULTS)
    if CONFIG.exists():
        cfg.update(json.loads(CONFIG.read_text(encoding="utf-8")))
    # CapCut's shared "adjust" effect resource (colour-grade sliders), next to the drafts folder
    cfg.setdefault("capcut_grade_cache", (Path(cfg["capcut_drafts"]).parents[1] / "Cache" / "effect" /
                                          "7501974767453474064" / "20cd8db6531c21bf7e4053026d20e395").as_posix())
    return cfg


PATHS = load()
TMP = Path(PATHS["tmp"])
BUILD = (TMP / "build").as_posix()

if __name__ == "__main__":
    print(json.dumps(PATHS, indent=1))
