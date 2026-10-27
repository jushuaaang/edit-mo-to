import json
import sys
import urllib.parse
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "gui"))
import feedback  # noqa: E402


def test_save_appends_with_at(tmp_path):
    e = feedback.save({"type": "suggestion", "title": "Más rápido", "text": "idea", "extra": "x"}, tmp_path)
    assert e["at"] and "extra" not in e and e["title"] == "Más rápido"
    feedback.save({"type": "bug", "title": "b", "text": "t", "step": "music"}, tmp_path)
    path = tmp_path / ".claude" / "edit-mo-to" / "feedback.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and json.loads(lines[0])["title"] == "Más rápido"
    assert [i["type"] for i in feedback.items(tmp_path)] == ["suggestion", "bug"]


def test_items_empty_when_missing(tmp_path):
    assert feedback.items(tmp_path) == []


@pytest.mark.parametrize("bad", [
    {"type": "rant", "title": "t", "text": "x"},
    {"type": "bug", "title": "", "text": "x"},
    {"type": "bug", "title": "t", "text": ""},
    {"type": "bug", "title": "t", "text": "x", "step": "nope"},
])
def test_save_rejects_bad(tmp_path, bad):
    with pytest.raises(ValueError):
        feedback.save(bad, tmp_path)


def test_issue_url():
    url = feedback.issue_url({"type": "suggestion", "title": "Add dark & light", "text": "Please", "step": "script"},
                             "abc1234", "Windows")
    assert url.startswith("https://github.com/jushuaaang/edit-mo-to/issues/new?")
    q = urllib.parse.parse_qs(url.split("?", 1)[1])
    assert q["title"] == ["Add dark & light"] and q["labels"] == ["enhancement"]
    body = q["body"][0]
    assert body.startswith("Please")
    assert "Step: script" in body and "edit-mo-to version: abc1234" in body and "OS: Windows" in body
    no_step = urllib.parse.parse_qs(feedback.issue_url({"type": "bug", "title": "t", "text": "x"}, "v", "macOS")
                                    .split("?", 1)[1])
    assert "Step:" not in no_step["body"][0] and no_step["labels"] == ["bug"]


def test_version_and_os(tmp_path):
    assert feedback.version(tmp_path / "not-a-repo") == "unknown"
    assert feedback.os_name() in ("Windows", "macOS") or feedback.os_name()
