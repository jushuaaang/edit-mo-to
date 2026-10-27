"""Claude's side of the companion GUI: keep `<video folder>/.edit-mo-to/job.json` current.

Every command prints one JSON line {"ok": true, ...}, or exits 1 with {"ok": false, "error": ...}.
Run as `.claude/edit-mo-to/run gui/job.py <command> ...` from the repo root.

    init <folder> --client C --product P [--resume]   create the job (refuses if one exists unless --resume)
    open <folder>                                     make this the job the GUI shows
    card <folder> key=value ...                       job card fields; timelines=a|b|c is a list;
                                                      temp_en=on|partial:<names>|removed|off
    step <folder> <step> <state> [--note T]           state: pending|working|waiting|done|skipped|error
    gate <folder> <step> --file gate.json             open a gate (ids g-1, g-2, ...), step -> waiting
        gate.json: {"title", "detail"?, "questions": [{"id", "text", "why"?, "kind", "options"?, "default"?}]}
    close-gate <folder>                               no gate open
    output <folder> <step> <kind> --file data.json    store a step output (table or checklist/script JSON)
    output <folder> <step> <kind> --from <adapter> <tool-output.json>
        adapters: timings, cuts, qa, clips, prompts (see adapters.py)
    log <folder> "<text>"                             activity line (last 200 kept)
    handled <folder> <seq> ...                        mark inbox events handled
    inbox <folder> [--unhandled] [--after N]          print the editor's events

init and open also make the folder the "current" job ({tmp}/gui/current.json).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adapters  # noqa: E402
import jobstate as js  # noqa: E402

LOG_KEEP = 200


def _read_json(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _log(job: dict, text: str) -> None:
    job["log"] = (job.get("log") or []) + [{"at": js._now(), "text": text}]
    job["log"] = job["log"][-LOG_KEEP:]


def _step(name: str) -> str:
    if name not in js.STEPS:
        raise ValueError(f"unknown step: {name!r} (one of {', '.join(js.STEPS)})")
    return name


def _check_temp_en(value: str) -> None:
    if value not in ("on", "removed", "off") and not (value.startswith("partial:") and value[8:].strip()):
        raise ValueError(f"temp_en must be on|partial:<names>|removed|off, got {value!r}")


def cmd_init(a) -> dict:
    folder = Path(a.folder)
    if js.state_dir(folder).joinpath("job.json").exists() and not a.resume:
        raise ValueError(f"{folder} already has a job; use --resume to keep it")
    folder.mkdir(parents=True, exist_ok=True)
    if not a.resume or not js.state_dir(folder).joinpath("job.json").exists():
        js.save(folder, js.new_job(folder, a.client, a.product))
    js.set_current(folder)
    return {"folder": folder.as_posix()}


def cmd_open(a) -> dict:
    js.load(Path(a.folder))  # fail loudly when there is no job
    js.set_current(Path(a.folder))
    return {"folder": Path(a.folder).as_posix()}


def cmd_card(a) -> dict:
    folder = Path(a.folder)
    job = js.load(folder)
    for pair in a.pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key:
            raise ValueError(f"expected key=value, got {pair!r}")
        if key == "temp_en":
            _check_temp_en(value)
        job["card"][key] = [t.strip() for t in value.split("|") if t.strip()] if key == "timelines" else value
    js.save(folder, job)
    return {"card": job["card"]}


def cmd_step(a) -> dict:
    folder = Path(a.folder)
    job = js.load(folder)
    step = job["steps"].setdefault(_step(a.step), {"state": "pending", "note": ""})
    step["state"] = a.state
    if a.note is not None:
        step["note"] = a.note
    js.save(folder, job)  # validate() rejects a state outside STATES
    return {"step": a.step, "state": a.state}


def _gate_from(spec: dict, gate_id: str, step: str) -> dict:
    if not isinstance(spec, dict) or not spec.get("title"):
        raise ValueError("gate file needs a title")
    questions = spec.get("questions") or []
    for i, q in enumerate(questions, 1):
        for field in ("id", "text", "kind"):
            if not q.get(field):
                raise ValueError(f"question {i} is missing {field}")
        if q["kind"] not in js.GATE_KINDS:
            raise ValueError(f"question {q['id']}: kind must be one of {js.GATE_KINDS}, got {q['kind']!r}")
    gate = {"id": gate_id, "step": step, "title": spec["title"], "text": spec["title"],
            "kind": questions[0]["kind"] if questions else "confirm", "questions": questions}
    if spec.get("detail"):
        gate["detail"] = spec["detail"]
    return gate


def cmd_gate(a) -> dict:
    folder = Path(a.folder)
    job = js.load(folder)
    _step(a.step)
    seq = int(job.get("gate_seq", 0)) + 1
    gate = _gate_from(_read_json(a.file), f"g-{seq}", a.step)
    if job.get("gate"):
        _log(job, f"gate {job['gate']['id']} replaced by {gate['id']}")
    job["gate_seq"], job["gate"] = seq, gate
    job["steps"][a.step]["state"] = "waiting"
    js.save(folder, job)
    return {"gate": gate["id"]}


def cmd_close_gate(a) -> dict:
    folder = Path(a.folder)
    job = js.load(folder)
    job["gate"] = None
    js.save(folder, job)
    return {}


def cmd_output(a) -> dict:
    folder = Path(a.folder)
    job = js.load(folder)
    _step(a.step)
    if bool(a.file) == bool(a.source):
        raise ValueError("give --file data.json or --from <adapter> <path>")
    if a.source:
        name, path = a.source
        if name not in adapters.ADAPTERS:
            raise ValueError(f"unknown adapter {name!r} (one of {', '.join(adapters.ADAPTERS)})")
        data = adapters.ADAPTERS[name](_read_json(path))
    else:
        data = _read_json(a.file)
    rel = f".edit-mo-to/outputs/{a.step}-{a.kind}.json"
    js._write_atomic(folder / rel, json.dumps(data, ensure_ascii=False, indent=2))
    job.setdefault("outputs", {}).setdefault(a.step, {})[a.kind] = {"path": rel, "at": js._now()}
    js.save(folder, job)
    return {"path": rel}


def cmd_log(a) -> dict:
    folder = Path(a.folder)
    job = js.load(folder)
    _log(job, a.text)
    js.save(folder, job)
    return {}


def cmd_handled(a) -> dict:
    folder = Path(a.folder)
    job = js.load(folder)
    job["handled"] = sorted(set(job.get("handled", [])) | set(a.seqs))
    js.save(folder, job)
    return {"handled": job["handled"]}


def cmd_inbox(a) -> dict:
    folder = Path(a.folder)
    events = js.unhandled(folder) if a.unhandled else js.read_events(folder)
    return {"events": [e for e in events if e["seq"] > a.after]}


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        _fail(message)


def _fail(message: str) -> None:
    print(json.dumps({"ok": False, "error": message}, ensure_ascii=False))
    sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True, parser_class=_Parser)

    def add(name, fn, *args, **opts):
        sp = sub.add_parser(name)
        sp.add_argument("folder")
        for flags, kw in args:
            sp.add_argument(*flags, **kw)
        sp.set_defaults(fn=fn)
        return sp

    add("init", cmd_init, (["--client"], {"required": True}), (["--product"], {"required": True}),
        (["--resume"], {"action": "store_true"}))
    add("open", cmd_open)
    add("card", cmd_card, (["pairs"], {"nargs": "+"}))
    add("step", cmd_step, (["step"], {}), (["state"], {"choices": js.STATES}), (["--note"], {}))
    add("gate", cmd_gate, (["step"], {}), (["--file"], {"required": True}))
    add("close-gate", cmd_close_gate)
    add("output", cmd_output, (["step"], {}), (["kind"], {}), (["--file"], {}),
        (["--from"], {"dest": "source", "nargs": 2, "metavar": ("ADAPTER", "PATH")}))
    add("log", cmd_log, (["text"], {}))
    add("handled", cmd_handled, (["seqs"], {"nargs": "+", "type": int}))
    add("inbox", cmd_inbox, (["--unhandled"], {"action": "store_true"}),
        (["--after"], {"type": int, "default": 0}))
    return p


def main(argv: list[str]) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    a = build_parser().parse_args(argv)
    try:
        result = a.fn(a)
    except FileNotFoundError as e:
        _fail(f"not found: {e.filename or e}")
    except (ValueError, KeyError, OSError) as e:  # ValueError covers bad JSON too
        _fail(f"{type(e).__name__}: {e}" if isinstance(e, KeyError) else str(e))
    print(json.dumps({"ok": True, **result}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
