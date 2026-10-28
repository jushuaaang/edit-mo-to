"""The workflow docs drive the companion GUI and run every tool through the `run` launcher (Task 11)."""
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
CLAUDE = ROOT / ".claude"
SKILL = CLAUDE / "skills" / "edit-mo-to" / "SKILL.md"
STEPS = CLAUDE / "skills" / "edit-mo-to" / "reference" / "steps.md"
CONTRACT = CLAUDE / "edit-mo-to" / "style-agent-contract.md"
PRACTICE = CLAUDE / "skills" / "practice-muna" / "SKILL.md"
README = ROOT / "README.md"


def _docs() -> list[Path]:
    """The shipped docs: every tracked .md under .claude/ (personal files are untracked), plus README.md."""
    out = subprocess.run(["git", "ls-files", "-z", "--", ".claude/*.md"], cwd=ROOT, capture_output=True, text=True,
                         check=True).stdout
    return sorted(ROOT / f for f in out.split("\0") if f) + [README]


def _text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")  # build-ledger.md has a stray non-UTF-8 byte


def test_no_old_style_tool_calls():
    old = '"{python}" "{root}/.claude/edit-mo-to/tools/'
    bad = [str(p.relative_to(ROOT)) for p in _docs() if old in _text(p)]
    assert not bad, f"old-style tool calls left in: {bad}"


def test_no_env_prefix_on_workflow_tools():
    # The allow rule is `Bash(.claude/edit-mo-to/run *)`: a PYTHONIOENCODING prefix or a {python} path in front of a
    # workflow tool would not match it (run sets PYTHONIOENCODING itself).
    pattern = re.compile(r'(PYTHONIOENCODING=utf-8\s+)?"\{python\}"\s+"?\{root\}/\.claude/edit-mo-to/(tools|gui)/')
    bad = [str(p.relative_to(ROOT)) for p in _docs() if pattern.search(_text(p))]
    assert not bad, bad


def test_run_launcher_form_used():
    for p in (SKILL, CONTRACT, PRACTICE, CLAUDE / "agents" / "editor.md", CLAUDE / "agents" / "qa.md",
              CLAUDE / "agents" / "motion-designer.md", CLAUDE / "skills" / "edit-mo-to" / "reference" / "learning.md"):
        assert ".claude/edit-mo-to/run tools/" in _text(p), p.name


def test_skill_mentions_gui_bridge():
    s = _text(SKILL)
    for needle in ("gui/launch.py", "gui/job.py gate", "gui/wait.py", "run_in_background"):
        assert needle in s, needle


def test_skill_has_gui_hard_rule_and_working_ahead():
    s = _text(SKILL)
    assert "**GUI.**" in s or "**GUI:**" in s
    for needle in ("close-gate", "handled", "job.py inbox \"<folder>\" --unhandled", '"early": true', "You chose", "default",
                   "never skip the gate", "Bash runs from `{root}`"):
        assert needle in s, needle


@pytest.mark.parametrize("qid", ["approve", "capcut_closed", "who", "broll_source", "generator", "source", "mode"])
def test_gate_question_ids_documented(qid):
    both = _text(SKILL) + _text(STEPS)
    assert f'"{qid}"' in both or f"`{qid}`" in both, qid


def test_steps_has_gate_json_and_outputs():
    s = _text(STEPS)
    for kind in ("choice", "multi", "text", "confirm", "file"):
        assert f'"kind": "{kind}"' in s, kind
    for out in ("checklist", "script", "timings", "cuts", "prompts", "clips", "qa"):
        assert re.search(rf"gui/job\.py output \"<folder>\" \w+ {out}\b", s), out
    for target in ("timing:apply-cuts", "review:changes", "learn:<id>", "voiceover:oldvo", "voiceover:oldvo-transcribe",
                   "storyboard:<id>:prompt", "brief:questions", "clips:check", "captions:auto-done", "export:learn"):
        assert target in s, target


def test_contract_storyboard_skeleton():
    c = _text(CONTRACT)
    assert '"prompt": null' in c
    assert "characters" in c
    assert "unless the editor chooses Approve anyway" in c
    assert "Never build the board before the images exist" not in c


def test_skill_storyboard_rule_changed():
    s = _text(SKILL)
    assert "unless the editor chooses Approve anyway" in s
    assert "Never build the board before the images exist" not in s


def test_readme_documents_the_app():
    r = _text(README)
    assert ".claude/edit-mo-to/run gui/launch.py --open" in r
    assert "Bash(.claude/edit-mo-to/run *)" in r or "allowlist" in r.lower()


def test_practice_opens_the_gui():
    assert "gui/launch.py" in _text(PRACTICE)
