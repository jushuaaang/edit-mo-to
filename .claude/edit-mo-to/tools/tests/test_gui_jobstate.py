import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "gui"))
import jobstate as js  # noqa: E402


def _job(folder: Path) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    job = js.new_job(folder, "Uvola", "Cereza")
    js.save(folder, job)
    return job


def test_new_job_has_every_step_pending(tmp_path):
    job = js.new_job(tmp_path, "C", "P")
    assert list(job["steps"]) == js.STEPS
    assert all(v == {"state": "pending", "note": ""} for v in job["steps"].values())
    assert job["gate"] is None and job["handled"] == [] and job["log"] == []
    assert job["card"] == {"client": "C", "product": "P", "folder": tmp_path.as_posix()}


def test_save_is_atomic_and_roundtrips(tmp_path):
    job = _job(tmp_path)
    got = js.load(tmp_path)
    job.pop("updated"), got.pop("updated")
    assert got == job
    assert not list(js.state_dir(tmp_path).glob("*.tmp"))


def test_load_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        js.load(tmp_path)


def test_validate_rejects_unknown_state(tmp_path):
    job = js.new_job(tmp_path, "C", "P")
    job["steps"]["brief"]["state"] = "bogus"
    with pytest.raises(ValueError, match="state"):
        js.validate(job)


def test_validate_rejects_unknown_step_and_bad_gate(tmp_path):
    job = js.new_job(tmp_path, "C", "P")
    job["steps"]["nope"] = {"state": "pending", "note": ""}
    with pytest.raises(ValueError, match="nope"):
        js.validate(job)
    del job["steps"]["nope"]
    def gate(*qs, **kw):
        return {"id": "g-1", "title": "T", "questions": list(qs), **kw}

    job["gate"] = gate({"id": "q", "text": "?", "kind": "weird"})
    with pytest.raises(ValueError, match="kind"):
        js.validate(job)
    job["gate"] = gate({"id": "q", "text": "?"})
    with pytest.raises(ValueError, match="kind"):
        js.validate(job)
    job["gate"] = gate({"id": "q", "kind": "text"})
    with pytest.raises(ValueError, match="text"):
        js.validate(job)
    job["gate"] = gate("not a dict")
    with pytest.raises(ValueError, match="object"):
        js.validate(job)
    job["gate"] = gate()
    with pytest.raises(ValueError, match="questions"):
        js.validate(job)
    job["gate"] = {"id": "g-1", "questions": [{"id": "q", "text": "?", "kind": "text"}]}
    with pytest.raises(ValueError, match="title"):
        js.validate(job)
    job["gate"] = gate({"id": "a", "text": "?", "kind": "choice"}, {"id": "b", "text": "?", "kind": "text"})
    js.validate(job)  # mixed kinds are fine


def test_events_get_increasing_seq_and_survive_reload(tmp_path):
    _job(tmp_path)
    evs = [js.append_event(tmp_path, {"type": "comment", "text": str(i)}) for i in range(3)]
    assert [e["seq"] for e in evs] == [1, 2, 3] and evs[0]["at"]
    assert [e["seq"] for e in js.read_events(tmp_path, after=1)] == [2, 3]
    assert [e["seq"] for e in js.read_events(tmp_path)] == [1, 2, 3]


def test_answer_to_closed_gate_is_stale(tmp_path):
    job = _job(tmp_path)
    job["gate"] = {"id": "g-1", "title": "ok?", "questions": [{"id": "q", "text": "ok?", "kind": "confirm"}]}
    js.save(tmp_path, job)
    assert "stale" not in js.append_event(tmp_path, {"type": "answer", "gate": "g-1"})
    job["gate"] = None
    js.save(tmp_path, job)
    assert js.append_event(tmp_path, {"type": "answer", "gate": "g-1"})["stale"] is True


def test_unhandled_excludes_handled(tmp_path):
    job = _job(tmp_path)
    for i in range(3):
        js.append_event(tmp_path, {"type": "comment", "text": str(i)})
    job["handled"] = [1]
    js.save(tmp_path, job)
    assert [e["seq"] for e in js.unhandled(tmp_path)] == [2, 3]


def test_listening_none_for_dead_pid(tmp_path):
    _job(tmp_path)
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    js.state_dir(tmp_path).joinpath("listening.json").write_text(
        json.dumps({"pid": p.pid, "since": "x", "step": "brief"}), encoding="utf-8")
    assert js.listening(tmp_path) is None
    js.write_listening(tmp_path, "script")
    got = js.listening(tmp_path)
    assert got["step"] == "script" and got["pid"] == os.getpid()
    js.clear_listening(tmp_path)
    assert js.listening(tmp_path) is None


def test_folder_with_spaces_and_accents(tmp_path):
    folder = tmp_path / "Uvola Cereza Ácida"
    job = _job(folder)
    assert js.load(folder)["folder"] == folder.as_posix()
    js.append_event(folder, {"type": "message", "text": "ñandú ✓"})
    assert js.read_events(folder)[0]["text"] == "ñandú ✓"
    js.write_listening(folder, None)
    assert js.listening(folder)["step"] is None
    assert job["card"]["folder"] == folder.as_posix()


def test_unicode_line_separators_roundtrip(tmp_path):
    _job(tmp_path)
    js.append_event(tmp_path, {"type": "comment", "text": "a b c\u0085d"})
    js.append_event(tmp_path, {"type": "comment", "text": "next"})
    evs = js.read_events(tmp_path)
    assert [e["seq"] for e in evs] == [1, 2]
    assert evs[0]["text"] == "a b c\u0085d"
    assert len(js.unhandled(tmp_path)) == 2


def test_torn_last_line_is_skipped_and_append_continues(tmp_path):
    _job(tmp_path)
    js.append_event(tmp_path, {"type": "comment", "text": "one"})
    inbox = js.state_dir(tmp_path) / "inbox.jsonl"
    with inbox.open("ab") as f:
        f.write(b'{"seq": 2, "at": "x", "ty')
    assert [e["seq"] for e in js.read_events(tmp_path)] == [1]
    assert js.append_event(tmp_path, {"type": "comment", "text": "two"})["seq"] == 2
    assert [e["text"] for e in js.read_events(tmp_path)] == ["one", "two"]


def test_bad_middle_line_still_raises(tmp_path):
    _job(tmp_path)
    js.append_event(tmp_path, {"type": "comment"})
    inbox = js.state_dir(tmp_path) / "inbox.jsonl"
    with inbox.open("ab") as f:
        f.write(b"garbage\n")
    js.append_event(tmp_path, {"type": "comment"})
    with pytest.raises(ValueError):
        js.read_events(tmp_path)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows sharing violation")
def test_save_retries_while_target_is_open(tmp_path):
    import threading
    import time
    job = _job(tmp_path)
    target = js.state_dir(tmp_path) / "job.json"
    ready = threading.Event()

    def hold():
        with open(target, "rb"):
            ready.set()
            time.sleep(0.1)

    t = threading.Thread(target=hold)
    t.start()
    ready.wait()
    js.save(tmp_path, job)
    t.join()
    assert js.load(tmp_path)["card"]["client"] == "Uvola"


def test_listening_needs_fresh_heartbeat(tmp_path):
    _job(tmp_path)
    path = js.write_listening(tmp_path, "brief")
    first = js.listening(tmp_path)
    assert first["step"] == "brief"
    js.write_listening(tmp_path, "script")
    assert js.listening(tmp_path)["since"] == first["since"]
    data = json.loads(path.read_text(encoding="utf-8"))
    data["beat"] -= 60
    path.write_text(json.dumps(data), encoding="utf-8")
    assert js.listening(tmp_path) is None
    assert js.listening(tmp_path, max_age=120)["pid"] == os.getpid()


@pytest.mark.parametrize("content", ['{"pid": "x", "beat": 1}', '{"pid": null, "beat": 1}', "[1, 2]",
                                     '{"pid": 1}', "not json"])
def test_listening_malformed_is_none(tmp_path, content):
    _job(tmp_path)
    (js.state_dir(tmp_path) / "listening.json").write_text(content, encoding="utf-8")
    assert js.listening(tmp_path) is None


def test_validate_non_dict_step_or_gate(tmp_path):
    job = js.new_job(tmp_path, "C", "P")
    job["steps"]["brief"] = "done"
    with pytest.raises(ValueError, match="brief"):
        js.validate(job)
    job["steps"]["brief"] = {"state": "done", "note": ""}
    job["gate"] = "open"
    with pytest.raises(ValueError, match="gate"):
        js.validate(job)


def test_append_event_rejects_unknown_type(tmp_path):
    _job(tmp_path)
    with pytest.raises(ValueError, match="type"):
        js.append_event(tmp_path, {"type": "bogus"})
    assert js.read_events(tmp_path) == []
