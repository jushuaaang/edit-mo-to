"""Learning step helper: propose only rules the editor does not already have and has not declined.

CLI (prints JSON; --root defaults to the edit-mo-to folder, where preferences.md lives):
    propose --patterns diff.json --notes notes.txt [--out proposals.json]
        diff.json is what `edit_diff.py diff` printed; notes.txt has one rule per line.
        -> {"proposals": [{rule, section, why}], "dropped": [{rule, matches}]}
    decline "<rule>"                      never offer this rule (or a close paraphrase) again
    save "<rule>" --section "B-roll" [--client name]
                                          add it to my-preferences.md (or clients/<name>.md)
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECLINED = "learning-declined.jsonl"
STOP = {"a", "an", "the", "of", "to", "and", "or", "in", "on", "at", "is", "it", "for", "by", "with", "be", "as"}


def normalise(rule: str) -> set[str]:
    s = re.sub(r"\[[^\]]*\]", " ", rule.lower())  # [client date] tags
    s = re.sub(r"\d+", "#", s)
    s = re.sub(r"[^a-z#\s]", " ", s)
    return {_stem(w) for w in s.split() if w not in STOP}


def _stem(w: str) -> str:
    """Light stemming: drop a trailing ing/es/ed/s on words longer than 4 letters (adds -> add)."""
    if len(w) > 4:
        for suf in ("ing", "es", "ed", "s"):
            if w.endswith(suf) and len(w) - len(suf) >= 3:
                return w[:-len(suf)]
    return w


def _similar(a: set[str], b: set[str], threshold: float) -> bool:
    """Jaccard >= threshold, or one rule almost wholly inside the other (a short paraphrase of a long rule)."""
    if not a or not b:
        return False
    both, small = len(a & b), min(len(a), len(b))
    return both / len(a | b) >= threshold or (small >= 3 and both / small >= 0.8)


def _matches(rule: str, existing: list[str], threshold: float) -> list[str]:
    n = normalise(rule)
    return [e for e in existing if _similar(n, normalise(e), threshold)]


def is_known(rule: str, existing: list[str], threshold: float = 0.6) -> str | None:
    m = _matches(rule, existing, threshold)
    return m[0] if m else None


def _bullets(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [l.strip() for l in path.read_text(encoding="utf-8").splitlines() if l.startswith("- ")]


def _declined(root: Path) -> list[str]:
    p = root / DECLINED
    if not p.exists():
        return []
    out = []
    for l in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(l)["rule"])
        except (ValueError, KeyError, TypeError):
            continue  # a hand-edited or half-written line must not stop the learning step
    return out


def existing_rules(root: Path) -> list[str]:
    out = _bullets(root / "preferences.md") + _bullets(root / "my-preferences.md")
    for f in sorted((root / "clients").glob("*.md")) if (root / "clients").is_dir() else []:
        out += _bullets(f)
    return out + _declined(root)


def _time(text: str) -> str:
    m = re.search(r"\d+:\d\d", text)
    return m.group(0) if m else "a little"


def _db(text: str) -> str:
    m = re.search(r"([\d.]+) dB", text)
    return m.group(1) if m else "a few"


def _rule(p: dict) -> tuple[str, str]:
    """(rule, section) for a recurring edit pattern, worded as 'next time ...'."""
    kind, _, what = p["id"].partition(":")
    label = {"b-roll": "B-roll", "a-roll": "A-roll", "vo": "VO", "sfx": "SFX"}.get(kind, kind.capitalize())
    section = "B-roll" if kind == "b-roll" else "Editing in CapCut"
    text, t = p["text"], _time(p["text"])
    rules = {
        "shorter": f"{label}: cut about {t} shorter than the VO span" if kind == "b-roll"
                   else f"{label}: cut clips about {t} shorter than first planned",
        "longer": f"{label}: hold clips about {t} longer than first planned",
        "earlier": f"{label}: place items about {t} earlier",
        "later": f"{label}: place items about {t} later",
        "to-cut": f"{label}: land items on a video cut",
        "louder": f"{label}: mix about {_db(text)} dB louder",
        "quieter": f"{label}: mix about {_db(text)} dB quieter",
        "zoom-in": f"{label}: scale clips bigger than first planned",
        "zoom-out": f"{label}: scale clips smaller than first planned",
        "reframed": f"{label}: re-position clips from the default framing",
        "speed": f"{label}: change clip speed from the default",
        "removed": f"{label}: leave out items the editor usually deletes",
        "added": f"{label}: add the extra items the editor usually adds",
    }
    return rules.get(what, f"{label}: {text}"), section


def candidates(patterns: list[dict], notes: list[str]) -> list[dict]:
    out, seen = [], set()
    for p in patterns:
        if p.get("count", 0) >= 2 or p.get("recurring"):
            rule, section = _rule(p)
            if rule not in seen:
                seen.add(rule)
                out.append({"rule": rule, "section": section, "why": p["text"]})
    for note in notes:
        note = note.strip()
        if note and note not in seen:
            seen.add(note)
            out.append({"rule": note, "section": "General", "why": note})
    return out


def propose(patterns: list[dict], notes: list[str], root: Path) -> dict:
    existing = existing_rules(root)
    proposals, dropped = [], []
    for c in candidates(patterns, notes):
        m = _matches(c["rule"], existing, 0.6)
        if m:
            dropped.append({"rule": c["rule"], "matches": m})
        else:
            proposals.append(c)
    return {"proposals": proposals, "dropped": dropped}


def decline(rule: str, root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with open(root / DECLINED, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"rule": rule}, ensure_ascii=False) + "\n")


def _skeleton(root: Path) -> str:
    pref = root / "preferences.md"
    heads = [l for l in pref.read_text(encoding="utf-8").splitlines() if l.startswith("## ")] if pref.exists() else []
    return "# my preferences\n\nYour own learned rules; these win over preferences.md.\n\n" + "".join(f"{h}\n\n" for h in heads)


def _add_bullet(text: str, section: str | None, rule: str) -> str:
    bullet = f"- {rule}"
    lines = text.rstrip("\n").split("\n") if text.strip() else []
    if section is None:
        return "\n".join(lines + [bullet]) + "\n"
    head = f"## {section}"
    if head not in lines:
        return "\n".join(lines + ["", head, bullet]) + "\n"
    i = lines.index(head) + 1
    end = i
    while end < len(lines) and not lines[end].startswith("## "):
        end += 1
    while end > i and not lines[end - 1].strip():
        end -= 1
    lines.insert(end, bullet)
    return "\n".join(lines) + "\n"


def save(rule: str, section: str, root: Path, client: str | None = None) -> Path:
    rule, section = " ".join(rule.split()), " ".join(section.split())
    if client:
        path = root / "clients" / (re.sub(r"[^\w.-]", "-", client.strip().lower()) + ".md")
        path.parent.mkdir(parents=True, exist_ok=True)
        text, sec = (path.read_text(encoding="utf-8") if path.exists() else f"# {client}\n\n"), None
    else:
        path = root / "my-preferences.md"
        text, sec = (path.read_text(encoding="utf-8") if path.exists() else _skeleton(root)), section
    path.write_text(_add_bullet(text, sec, rule), encoding="utf-8")
    return path


def _opt(argv, name):
    if name in argv:
        i = argv.index(name)
        v = argv[i + 1]
        del argv[i:i + 2]
        return v
    return None


def main(argv: list[str]) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")   # Windows consoles default to cp1252
    argv = list(argv)
    cmd = argv.pop(0) if argv else ""
    root = Path(_opt(argv, "--root") or ROOT)
    if cmd == "propose":
        diff = json.loads(Path(_opt(argv, "--patterns")).read_text(encoding="utf-8"))
        notes_p, out = _opt(argv, "--notes"), _opt(argv, "--out")
        notes = Path(notes_p).read_text(encoding="utf-8").splitlines() if notes_p else []
        patterns = diff.get("patterns", []) if isinstance(diff, dict) else diff
        rec = {r["id"] for r in diff.get("recurring", [])} if isinstance(diff, dict) else set()
        patterns = [{**p, "recurring": True} if p.get("id") in rec else p for p in patterns]
        res = propose(patterns, notes, root)
        if out:
            Path(out).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    elif cmd == "decline":
        decline(argv[0], root)
        res = {"declined": argv[0]}
    elif cmd == "save":
        section, client = _opt(argv, "--section") or "General", _opt(argv, "--client")
        res = {"saved": str(save(argv[0], section, root, client))}
    else:
        raise SystemExit(__doc__)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
