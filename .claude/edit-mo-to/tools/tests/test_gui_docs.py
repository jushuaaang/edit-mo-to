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


@pytest.mark.parametrize("qid", ["approve", "capcut_closed", "who", "broll_source", "generator", "generator_model", "source",
                                 "mode"])
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


def test_gate_waits_for_every_required_answer():
    both = _text(SKILL) + _text(STEPS)
    assert "wait.py --after <the new highest seq>" in both
    assert "until every required question has an answer" in _text(SKILL)
    assert "until every question the gate needs is answered" in _text(STEPS)
    assert "only when `approve` is `false`" in both  # conditional questions are marked
    assert "message, edit or upload" in _text(SKILL)  # non-answers are handled, then wait again


def test_early_confirm_meaning_documented():
    for doc in (_text(SKILL), _text(STEPS)):
        assert "`source_ok`" in doc or '"source_ok"' in doc
        assert "`true` means use the early value" in doc or "Answer `true`: use the early value" in doc
        assert "`false` means" in doc or "Answer `false`:" in doc
    assert '{"id": "source", "kind": "confirm"' not in _text(STEPS)


def test_no_shell_redirects_or_mkdir_in_tool_calls():
    """`>` and mkdir don't match the run allow rule: the tools take --out and create their own folders."""
    redirect = re.compile(r'\.py\b[^`\n]*?\s>>?\s*"')
    bad = [str(p.relative_to(ROOT)) for p in _docs() if redirect.search(_text(p))]
    assert not bad, bad
    for p in _docs():
        assert "create the `inv` folder first" not in _text(p), p
    s = _text(SKILL)
    assert 'qa_check.py build "{tmp}/reports/<job>/plan.json"' in s and '--out "{tmp}/reports/<job>/qa_check.json"' in s
    assert '--out "{tmp}/reports/<job>/inv/inventory.json"' in s


def test_job_calls_one_at_a_time_and_stdin_gate():
    s, st = _text(SKILL), _text(STEPS)
    assert "one at a time" in st
    assert "--file - <<'JSON'" in st and "--file -" in s


def test_wait_is_rerun_after_a_timeout():
    for doc in (_text(SKILL), _text(STEPS)):
        assert "same `--after`" in doc
        assert "longest background timeout" in doc


def test_actions_never_replace_a_gate():
    s, st = _text(SKILL), _text(STEPS)
    assert "as the approval gate" not in st
    for doc in (s, st):
        assert "never replaces a gate" in doc
    assert "count like early inputs" in st


def test_character_sheet_gate_is_a_confirm():
    st = _text(STEPS)
    assert "`character_sheet` (confirm" in st
    assert "`CHAR-1`, `CHAR-2`… (file" not in st


def test_board_keeps_beat_ids():
    c = _text(CONTRACT)
    assert "Keep each beat's `id`, `en`, `prompt`, `status` and `visual`" in c


def test_readme_gui_section_is_accurate():
    r = _text(README)
    assert "run this in your Video Editing folder (`{root}`)" in r
    assert "no deletes" not in r


def test_generator_gate_is_higgsfield_or_google_flow():
    """Higgsfield replaces Seedance (spec "Generator: Higgsfield replaces Seedance")."""
    site = "Where will you generate: Higgsfield or Google Flow?"
    for doc in (_text(SKILL), _text(STEPS)):
        assert site in doc and "Which Higgsfield model?" in doc
    st = _text(STEPS)
    assert ('{"value": "higgsfield", "label": "Higgsfield"}, {"value": "google-flow", "label": "Google Flow"}' in st)
    assert '{"id": "generator_model", "kind": "choice", "text": "Which Higgsfield model?"' in st
    assert '{"value": "other", "label": "Other"}' in st
    assert "`generator_model` once `generator` is answered (both sites ask it)" in st   # Task H2: either site asks the model
    assert "prompts:generator_model" in st
    bad = [str(p.relative_to(ROOT)) for p in _docs() if "Seedance or Google Flow" in _text(p)
           or "google-flow|seedance" in _text(p) or "google-flow | seedance" in _text(p)]
    assert not bad, bad
    assert "--generator higgsfield|google-flow" in _text(SKILL) and "--model" in _text(SKILL)


def test_model_question_follows_either_site():
    """Task H2: Google Flow asks the model too ("Which Google Flow model?"); every other generator line stays."""
    for doc in (_text(SKILL), _text(STEPS)):
        assert "Which Google Flow model?" in doc and "Which Higgsfield model?" in doc
        assert "Where will you generate: Higgsfield or Google Flow?" in doc
    st = _text(STEPS)
    assert '{"id": "generator_model", "kind": "choice", "text": "Which Google Flow model?"' in st
    assert '{"value": "veo-3.1-fast", "label": "Veo 3.1 Fast"}' in st
    assert "only when `generator` is `higgsfield`" not in st
    assert "for either site" in _text(SKILL) or "either site" in st
    assert "generator=Google Flow · <model label>" in _text(SKILL)


# --- Task B2: Claude detects the editor's language and sets the app (spec "Beginner friendly", Auto-detect) ---

LANG_RULE = ("reply in the editor's language (English, Taglish or Tagalog). When the editor writes in Taglish or Tagalog, "
             "run `.claude/edit-mo-to/run gui/job.py lang tl` once; when they switch back to English, `… lang en`. "
             "Never translate the script, the VO, the generator prompts or the editor's text.")


@pytest.mark.parametrize("doc", [SKILL, PRACTICE], ids=["edit-mo-to", "practice-muna"])
def test_language_rule_in_the_skills(doc):
    s = _text(doc)
    assert "**Language:**" in s and LANG_RULE in s
    assert "job.py card ui_lang" not in s  # the language is per computer (job.py lang), not on a job card


@pytest.mark.parametrize("doc", [SKILL, PRACTICE], ids=["edit-mo-to", "practice-muna"])
def test_gate_lines_unchanged(doc):
    """Every ⛔ line of the committed skill is still there word for word (B2 adds a rule, it never rewords a gate)."""
    rel = doc.relative_to(ROOT).as_posix()
    head = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if head.returncode:
        pytest.skip("not in git")
    now = _text(doc).splitlines()
    gone = [l for l in head.stdout.splitlines() if "⛔" in l and l not in now]
    assert not gone, gone

