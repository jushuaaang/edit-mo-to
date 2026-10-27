import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "gui"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jobstate as js  # noqa: E402
import pytest  # noqa: E402

JOB = Path(__file__).resolve().parents[2] / "gui" / "job.py"


@pytest.fixture(autouse=True)
def _isolated_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("EDIT_MO_TO_GUI_TMP", str(tmp_path / "guitmp"))  # subprocesses inherit it


def run(*args, ok=True):
    p = subprocess.run([sys.executable, str(JOB), *map(str, args)], capture_output=True, text=True,
                       encoding="utf-8")
    out = json.loads(p.stdout.strip().splitlines()[-1])
    assert (p.returncode == 0) == ok, p.stdout + p.stderr
    assert out["ok"] is ok
    return out


def init(tmp_path):
    folder = tmp_path / "vid"
    run("init", folder, "--client", "Uvola", "--product", "Cereza")
    return folder


def test_init_then_step_and_card(tmp_path):
    folder = init(tmp_path)
    run("step", folder, "storyboard", "waiting", "--note", "hi")
    run("card", folder, "language=es", "timelines=Hook 1|Hook 2", "temp_en=on")
    job = js.load(folder)
    assert job["steps"]["storyboard"] == {"state": "waiting", "note": "hi"}
    assert job["card"]["language"] == "es" and job["card"]["temp_en"] == "on"
    assert job["card"]["timelines"] == ["Hook 1", "Hook 2"]
    run("init", folder, "--client", "A", "--product", "B", ok=False)
    run("init", folder, "--client", "A", "--product", "B", "--resume")


def test_bad_step_state_and_card_fail(tmp_path):
    folder = init(tmp_path)
    run("step", folder, "storyboard", "bogus", ok=False)
    run("step", folder, "storyboard", "done")
    run("card", folder, "temp_en=maybe", ok=False)
    run("card", folder, "noequals", ok=False)
    run("card", folder, "temp_en=partial:Hook 1")


def test_gate_sets_step_waiting_and_ids_increase(tmp_path):
    folder = init(tmp_path)
    g = tmp_path / "g.json"
    g.write_text(json.dumps({"title": "Pick", "questions": [
        {"id": "q1", "text": "Which?", "kind": "choice", "options": ["a", "b"]}]}), encoding="utf-8")
    out = run("gate", folder, "script", "--file", g)
    assert out["gate"] == "g-1"
    job = js.load(folder)
    assert job["steps"]["script"]["state"] == "waiting" and job["gate"]["id"] == "g-1"
    out = run("gate", folder, "script", "--file", g)
    assert out["gate"] == "g-2" and any("replac" in l["text"] for l in js.load(folder)["log"])
    run("close-gate", folder)
    assert js.load(folder)["gate"] is None
    assert run("gate", folder, "script", "--file", g)["gate"] == "g-3"


def test_bad_gate_file_fails_loudly(tmp_path):
    folder = init(tmp_path)
    g = tmp_path / "g.json"
    g.write_text(json.dumps({"title": "Pick", "questions": [{"id": "q1", "text": "Which?"}]}), encoding="utf-8")
    out = run("gate", folder, "script", "--file", g, ok=False)
    assert "kind" in out["error"]


def test_output_from_qa_adapter(tmp_path):
    folder = init(tmp_path)
    qa = tmp_path / "qa.json"
    rows = [{"n": i, "check": "c", "status": s, "evidence": "e", "fix": "f", "timeline": "t"}
            for i, s in enumerate(["PASS", "FAIL", "OPEN"], 1)]
    qa.write_text(json.dumps({"rows": rows, "passed": 1, "verdict": "FAIL (1 issues)"}), encoding="utf-8")
    run("output", folder, "build", "qa", "--from", "qa", qa)
    rec = js.load(folder)["outputs"]["build"]["qa"]
    stored = json.loads((folder / rec["path"]).read_text(encoding="utf-8"))
    assert [r["status"] for r in stored["rows"]] == ["ok", "err", "you"]
    assert rec["at"]
    run("output", folder, "build", "qa", "--from", "nope", qa, ok=False)


def _file(tmp_path, data, name="d.json"):
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_output_file_shapes(tmp_path):
    folder = init(tmp_path)
    script = {"lang": "es", "temp_en": True, "lines": [{"id": "l1", "text": "Hola", "en": "Hi"}]}
    run("output", folder, "script", "script", "--file", _file(tmp_path, script))
    assert "script" in js.load(folder)["outputs"]["script"]
    checklist = {"style": "ugc", "language": "en", "rules": [{"n": 1, "rule": "r", "source": "s", "status": "ok"}],
                 "questions": []}
    run("output", folder, "brief", "checklist", "--file", _file(tmp_path, checklist))
    table = {"title": "T", "columns": ["A", "B"], "rows": [{"id": "1", "cells": ["x", "y"]}]}
    run("output", folder, "build", "custom", "--file", _file(tmp_path, table))

    bad = run("output", folder, "script", "script", "--file", _file(tmp_path, {**script, "temp_en": "yes"}), ok=False)
    assert "temp_en" in bad["error"]
    bad = run("output", folder, "brief", "checklist", "--file",
              _file(tmp_path, {**checklist, "rules": [{"n": 1, "rule": "r"}]}), ok=False)
    assert "source" in bad["error"]
    bad = run("output", folder, "build", "custom", "--file",
              _file(tmp_path, {**table, "rows": [{"id": "1", "cells": ["x"]}]}), ok=False)
    assert "cells" in bad["error"]
    bad = run("output", folder, "build", "custom", "--file", _file(tmp_path, {"columns": []}), ok=False)
    assert "title" in bad["error"]


def test_output_kind_is_sanitized(tmp_path):
    folder = init(tmp_path)
    table = {"title": "T", "columns": ["A"], "rows": []}
    out = run("output", folder, "build", "../evil", "--file", _file(tmp_path, table), ok=False)
    assert "kind" in out["error"]


def test_malformed_input_prints_json_error(tmp_path):
    folder = init(tmp_path)
    run("gate", folder, "script", "--file", _file(tmp_path, ["not", "an", "object"]), ok=False)
    run("gate", folder, "script", "--file", _file(tmp_path, {"title": "T", "questions": ["x"]}), ok=False)
    run("gate", folder, "script", "--file", _file(tmp_path, {"title": "T", "questions": []}), ok=False)
    run("output", folder, "build", "qa", "--from", "qa", _file(tmp_path, [1, 2]), ok=False)


def test_mixed_kind_gate_accepted(tmp_path):
    folder = init(tmp_path)
    g = {"title": "Mixed", "questions": [{"id": "a", "text": "?", "kind": "choice"},
                                         {"id": "b", "text": "?", "kind": "text"}]}
    assert run("gate", folder, "script", "--file", _file(tmp_path, g))["gate"] == "g-1"


def test_folder_is_resolved(tmp_path, monkeypatch):
    (tmp_path / "sub").mkdir()
    monkeypatch.chdir(tmp_path)
    run("init", "sub/../vid", "--client", "A", "--product", "B")
    assert js.load(tmp_path / "vid")["folder"] == (tmp_path / "vid").resolve().as_posix()


def test_run_launcher_help():
    import shutil
    if not shutil.which("sh"):
        pytest.skip("no sh")
    root = Path(__file__).resolve().parents[4]
    p = subprocess.run(["sh", ".claude/edit-mo-to/run", "gui/job.py", "--help"], cwd=root,
                       capture_output=True, text=True)
    assert p.returncode == 0 and "init" in p.stdout


def test_init_and_open_set_current(tmp_path):
    folder = init(tmp_path)
    other = tmp_path / "other"
    run("init", other, "--client", "A", "--product", "B")
    run("open", folder)
    cur = json.loads((tmp_path / "guitmp" / "gui" / "current.json").read_text(encoding="utf-8"))
    assert cur == {"folder": folder.as_posix()}
    run("open", tmp_path / "nojob", ok=False)


def test_log_appends(tmp_path):
    folder = init(tmp_path)
    for i in range(3):
        run("log", folder, f"line {i}")
    assert [l["text"] for l in js.load(folder)["log"]] == ["line 0", "line 1", "line 2"]


def test_inbox_unhandled(tmp_path):
    folder = init(tmp_path)
    js.append_event(folder, {"type": "comment", "text": "a"})
    js.append_event(folder, {"type": "comment", "text": "b"})
    run("handled", folder, 1)
    out = run("inbox", folder, "--unhandled")
    assert [e["seq"] for e in out["events"]] == [2]
    assert [e["seq"] for e in run("inbox", folder, "--after", 1)["events"]] == [2]
    assert len(run("inbox", folder)["events"]) == 2


def test_current_job_roundtrip(tmp_path, monkeypatch):
    import machine
    monkeypatch.delenv("EDIT_MO_TO_GUI_TMP")
    monkeypatch.setitem(machine.PATHS, "tmp", str(tmp_path / "t"))
    folder = tmp_path / "vid"
    folder.mkdir()
    assert js.get_current() is None
    js.set_current(folder)
    assert js.get_current() == folder.as_posix()
    cur = tmp_path / "t" / "gui" / "current.json"
    assert json.loads(cur.read_text(encoding="utf-8")) == {"folder": folder.as_posix()}
