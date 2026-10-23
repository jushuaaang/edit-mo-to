"""Context pack: only the rules one agent dispatch needs, instead of the whole preferences file.

usage: python context_pack.py <style> [--client name] [--generator google-flow|seedance] --out pack.md
prints {"pack", "chars", "sections"}. Style: ugc | broll | claymation | pixar | product-ad.
Sections come from preferences.md by `## ` heading; the editor's my-preferences.md follows
under its own header (wins on conflict), then the client file.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from machine import ROOT  # noqa: E402

STYLES = {"ugc": "UGC", "broll": "B-roll", "claymation": "Claymation", "pixar": "Pixar", "product-ad": "Product ad"}
GENERATORS = {"google-flow": "Google Flow", "flow": "Google Flow", "seedance": "Seedance"}


def _sections(text: str) -> dict[str, str]:
    """`## ` heading -> its full block (heading line included)."""
    out, name, buf = {}, None, []
    for line in text.splitlines():
        m = re.match(r"##\s+(.+?)\s*$", line)
        if m:
            if name:
                out[name] = "\n".join(buf).rstrip()
            name, buf = m.group(1), [line]
        elif name:
            buf.append(line)
    if name:
        out[name] = "\n".join(buf).rstrip()
    return out


def _pick(secs: dict[str, str], wanted: list[str]) -> list[tuple[str, str]]:
    """Wanted headings in order; 'Known generation failures' matches by prefix."""
    picked = []
    for w in wanted:
        for name, block in secs.items():
            if name == w or (w.endswith("failures") and name.startswith(w)):
                picked.append((name, block))
                break
    return picked


def _build(style: str, client: str | None, generator: str | None, root: Path) -> tuple[str, list[str]]:
    base = root / ".claude" / "edit-mo-to"
    wanted = ["General", "Prompts (all generators)"]
    if generator:
        wanted.append(GENERATORS[generator.lower()])
    wanted += [STYLES[style.lower()], "Editing in CapCut", "Known generation failures"]
    names, parts = [], []
    for name, block in _pick(_sections((base / "preferences.md").read_text(encoding="utf-8")), wanted):
        names.append(name)
        parts.append(block)
    mine = base / "my-preferences.md"
    if mine.exists():
        own = _pick(_sections(mine.read_text(encoding="utf-8")), wanted)
        if own:
            parts.append("# Editor's own rules (win on conflict)\n\n" + "\n\n".join(b for _, b in own))
            names += [f"mine:{n}" for n, _ in own]
    if client:
        cf = base / "clients" / f"{client}.md"
        if cf.exists():
            parts.append("# Client\n\n" + cf.read_text(encoding="utf-8").strip())
            names.append(f"client:{client}")
    return "\n\n".join(parts) + "\n", names


def build_pack(style: str, client: str | None = None, generator: str | None = None, root: Path = ROOT) -> str:
    return _build(style, client, generator, Path(root))[0]


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("style", choices=sorted(STYLES))
    ap.add_argument("--client")
    ap.add_argument("--generator", choices=sorted(GENERATORS))
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    pack, names = _build(a.style, a.client, a.generator, ROOT)
    Path(a.out).write_text(pack, encoding="utf-8")
    print(json.dumps({"pack": a.out, "chars": len(pack), "sections": names}))


if __name__ == "__main__":
    main(sys.argv[1:])
