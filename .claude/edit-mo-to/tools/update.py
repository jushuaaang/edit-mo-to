"""Update edit-mo-to: pull the newest version, then install what the new version needs.

What it does, in order (the editor says "update edit-mo-to"; never run it on your own):
  1. `git pull --ff-only` in {root} (stops here if git refuses: local changes or a diverged branch).
  2. `pip install -r tools/requirements.txt` with this Python (run it with {python}, the tools' venv). Always, not
     only when requirements.txt changed in this pull: a package added by an earlier pull may never have been
     installed. Packages already there are left as they are, so it is quick.
  3. `npm ci` in motion/ (HyperFrames) when this pull changed motion/package.json or package-lock.json.
Your own files (my-preferences.md, clients/, edit-patterns.jsonl, machine.json, videos) are never touched.

usage: {python} update.py [--root DIR]      prints JSON: commits pulled, files changed, each install step's result
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
NPM_FILES = (".claude/edit-mo-to/motion/package.json", ".claude/edit-mo-to/motion/package-lock.json")


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def _tail(p: subprocess.CompletedProcess, n: int = 600) -> str:
    return ((p.stderr or "") + (p.stdout or "")).strip()[-n:]


def update(root: Path, run=_run, python: str = sys.executable) -> dict:
    git = ["git", "-C", str(root)]
    old = run(git + ["rev-parse", "HEAD"]).stdout.strip()
    pull = run(git + ["pull", "--ff-only"])
    if pull.returncode:
        return {"ok": False, "step": "git pull", "error": _tail(pull)}
    new = run(git + ["rev-parse", "HEAD"]).stdout.strip()
    commits = run(git + ["log", "--oneline", f"{old}..{new}"]).stdout.strip().splitlines() if old != new else []
    files = run(git + ["diff", "--name-only", old, new]).stdout.strip().splitlines() if old != new else []
    out = {"ok": True, "pulled": len(commits), "commits": commits, "files": files}

    pip = run([python, "-m", "pip", "install", "-q", "--disable-pip-version-check", "-r", str(TOOLS / "requirements.txt")])
    out["python_packages"] = "ok" if pip.returncode == 0 else f"failed: {_tail(pip)}"
    out["ok"] = out["ok"] and pip.returncode == 0

    if any(f in NPM_FILES for f in files):
        npm = shutil.which("npm") or "npm"
        r = run([npm, "ci"], cwd=root / ".claude" / "edit-mo-to" / "motion")
        out["hyperframes"] = "ok (npm ci)" if r.returncode == 0 else f"failed: {_tail(r)}"
        out["ok"] = out["ok"] and r.returncode == 0
    else:
        out["hyperframes"] = "unchanged"
    return out


def main(argv: list[str]) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if argv and argv[0] in ("-h", "--help"):
        raise SystemExit(__doc__)
    root = Path(argv[argv.index("--root") + 1]) if "--root" in argv else TOOLS.parents[2]
    res = update(root)
    print(json.dumps(res, indent=1, ensure_ascii=False))
    raise SystemExit(0 if res["ok"] else 1)


if __name__ == "__main__":
    main(sys.argv[1:])
