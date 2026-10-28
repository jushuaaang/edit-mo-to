"""AI-clip generator rules: the one loader for `.claude/edit-mo-to/generators.json`.

plan_tools (prompt checks and the start line), context_pack (the generator's limits in the pack), qa_check and the
GUI server read the table through here, so no tool or page keeps its own copy of the rules.

    rules(generator, model=None) -> dict      one row, normalised (see _row), plus "generator", "model", "label",
                                              "warning" (None, or the one line Claude says when the limits are
                                              not verified or the model is unknown)
    for_spec(spec) -> dict                    the same for a prompts2 spec (`generator`, `generator_model`, old `mode`)
    length_error(rule, seconds) -> str|None   why a generated length breaks the row, or None
    strictest() -> dict                       the fallback limits for an unknown model {min_s, max_s, max_attach}
"""
import json
from functools import lru_cache
from pathlib import Path

FILE = Path(__file__).resolve().parents[1] / "generators.json"
DEFAULT = "google-flow"   # a spec with no generator has always been checked with the Flow limits
KEYS = ("min_s", "max_s", "lengths_s", "max_attach", "start_frame", "start_line", "end_frame", "verified", "notes", "prefs")


@lru_cache(maxsize=4)
def _load(path: str, mtime: float) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load(path: Path = FILE) -> dict:
    """The whole table (re-read when the file changes)."""
    p = Path(path)
    return _load(str(p), p.stat().st_mtime)


def names(path: Path = FILE) -> list[str]:
    """Every generator name a tool accepts: the table's keys and the old aliases (`seedance`, `flow`)."""
    t = load(path)
    return sorted({*t["generators"], *t.get("aliases", {})})


def _row(raw: dict) -> dict:
    return {k: raw.get(k) for k in KEYS} | {"prefs": list(raw.get("prefs") or [])}


def _range(r: dict) -> "tuple[float | None, float | None]":
    if r.get("lengths_s"):
        return min(r["lengths_s"]), max(r["lengths_s"])
    return r.get("min_s"), r.get("max_s")


def _strictest(t: dict) -> dict:
    """The fallback limits: the longest minimum, shortest maximum and smallest attachment cap in the table."""
    rows = []
    for g in t["generators"].values():
        rows += list(g["models"].values()) if "models" in g else [g]
    los, his = zip(*(_range(r) for r in rows))
    caps = [r["max_attach"] for r in rows if r.get("max_attach") is not None]
    return {"min_s": max((x for x in los if x is not None), default=None),
            "max_s": min((x for x in his if x is not None), default=None),
            "max_attach": min(caps, default=None)}


def strictest(path: Path = FILE) -> dict:
    """{min_s, max_s, max_attach}: the safe limits Claude uses for a model the table does not know (the GUI shows them)."""
    return _strictest(load(path))


def _fmt(x) -> str:
    return f"{x:g}"


def _limits(r: dict) -> str:
    if r.get("lengths_s"):
        length = ", ".join(_fmt(x) for x in r["lengths_s"][:-1]) + f" or {_fmt(r['lengths_s'][-1])} s"
    else:
        length = f"{_fmt(r['min_s'])}–{_fmt(r['max_s'])} s"
    return f"{length}, at most {r['max_attach']} attachments"


def rules(generator: "str | None", model: "str | None" = None, path: Path = FILE) -> dict:
    t = load(path)
    gens, aliases = t["generators"], t.get("aliases", {})
    gen = (generator or DEFAULT).strip().lower()
    warning = None
    if gen in aliases:
        model = model or aliases[gen].get("model")
        gen = aliases[gen]["generator"]
    if gen not in gens:
        warning = f"unknown generator {generator!r}; using the {gens[DEFAULT]['label']} limits from generators.json"
        gen = DEFAULT
    site = gens[gen]
    if "models" not in site:
        r = _row(site) | {"generator": gen, "model": None, "label": site["label"]}
    else:
        key = (model or "").strip()
        hit = next((k for k, m in site["models"].items() if key.lower() in (k.lower(), m["label"].lower())), None)
        hit = hit or site.get("aliases", {}).get(key.lower())   # "Seedance", "Kling": a name without a version
        if hit:
            r = _row(site["models"][hit]) | {"generator": gen, "model": hit,
                                             "label": f"{site['label']} · {site['models'][hit]['label']}"}
        else:
            fb = site["fallback"]
            r = _row(fb) | _strictest(t) | {"generator": gen, "model": key or None, "verified": None,
                                            "label": f"{site['label']} · {key or fb['label']}"}
            if key:
                warning = (f"{r['label']} is not in generators.json; using the strictest limits in the table "
                           f"({_limits(r)}); add the model's row to generators.json")
            else:
                warning = (f"no {site['label']} model given (generator_model); using the strictest limits in the "
                           f"table ({_limits(r)})")
    if warning is None and r["verified"] is None:
        warning = f"limits for {r['label']} are not verified; check them in generators.json"
    return r | {"warning": warning}


def for_spec(spec: dict, path: Path = FILE) -> dict:
    """A prompts2 spec's rules. Old specs: "seedance" as `generator` or `mode` = Higgsfield · Seedance 2.0 (today's
    Seedance rules); "flow" = Google Flow."""
    gen, mode = spec.get("generator"), spec.get("mode")
    if gen != "higgsfield" and "seedance" in (gen, mode):
        gen = "seedance"
    return rules(gen, spec.get("generator_model"), path)


def length_error(r: dict, seconds) -> "str | None":
    if r.get("lengths_s"):
        if seconds not in r["lengths_s"]:
            opts = ", ".join(_fmt(x) for x in r["lengths_s"][:-1]) + f" or {_fmt(r['lengths_s'][-1])} s"
            return f"{r['label']} generates only {opts} clips, got {_fmt(seconds)} s"
        return None
    lo, hi = r.get("min_s"), r.get("max_s")
    if lo is not None and hi is not None and not lo <= seconds <= hi:
        return f"{r['label']} generation must be {_fmt(lo)}–{_fmt(hi)} s, got {_fmt(seconds)} s"
    if hi is None and lo is not None and seconds < lo:
        return f"{r['label']} clips must be at least {_fmt(lo)} s, got {_fmt(seconds)} s"
    if lo is None and hi is not None and seconds > hi:
        return f"{r['label']} clips must be at most {_fmt(hi)} s, got {_fmt(seconds)} s"
    return None


def describe(r: dict) -> str:
    """The rules as a few lines for a context pack."""
    if r.get("lengths_s"):
        length = "fixed lengths " + ", ".join(_fmt(x) for x in r["lengths_s"]) + " s (take the next one up, trim in the edit)"
    elif r.get("min_s") is not None and r.get("max_s") is not None:
        length = f"{_fmt(r['min_s'])}–{_fmt(r['max_s'])} s"
    elif r.get("min_s") is not None:
        length = f"at least {_fmt(r['min_s'])} s"
    else:
        length = "no limit in the table"
    lines = [f"## Generator: {r['label']} (from generators.json)",
             f"- Clip length: {length}.",
             f"- Attachments: {'no cap' if r.get('max_attach') is None else f'at most {r['max_attach']}'}.",
             f"- Start frame: {'yes' if r.get('start_frame') else 'no'}; end frame: {'yes' if r.get('end_frame') else 'no'}.",
             f"- Video prompts start with: {r['start_line']!r} (plan_tools.py prompts adds it)." if r.get("start_line")
             else "- No start line is added to video prompts."]
    if r.get("notes"):
        lines.append(f"- Notes: {r['notes']}")
    if r.get("warning"):
        lines.append(f"- Warning: {r['warning']}. Say so in chat.")
    return "\n".join(lines)
