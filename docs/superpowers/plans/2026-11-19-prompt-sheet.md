# Prompt Sheet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One self-contained HTML "prompt sheet" per job (character sheets, keyframes, clip prompts, running order) with Copy/Done per card, published as an Artifact; chat no longer carries prompt text.

**Architecture:** New `tools/prompt_sheet.py` reads `<folder>/storyboard/storyboard.json` and any `prompts2.json` specs, reuses `plan_tools._block`, `_plain`, `_line_text`, `to_sf` for text, embeds the cards as JSON in one HTML template string. Workflow docs switch the "paste prompts" rule to "table + sheet link".

**Tech Stack:** Python 3 stdlib, pytest, vanilla HTML/JS.

**Spec:** `docs/superpowers/specs/2026-11-19-prompt-sheet-design.md`

## Global Constraints
- Copy text of a clip card == `plan_tools._block(spec, p)` byte for byte; storyboard card == beat/character `prompt`.
- Times in `seconds:frames` (30 fps) via `media_timing.to_sf`.
- No external scripts/fonts; light + dark; works at 375 px wide; clipboard failure falls back to selecting the `<pre>`.
- Done ticks in `localStorage` under `promptsheet:<job>`, wrapped in try/catch.
- Never commit personal files (`my-preferences.md`, `clients/`, `edit-patterns.jsonl`, `_practice/`).

## Review Focus
- Prompt text containing `</script>` or HTML → must not break the page (escape `<` in embedded JSON). Test in Task 1.
- Character ad first phase: beats with `"prompt": null` → no card, Keyframes section says "after the character sheet". Test in Task 1.
- Folder with no storyboard and no specs → exit 2 with a clear message. Test in Task 1.
- Several specs (one per timeline) → one Clips group per spec, titled by its `job`/file stem. Test in Task 1.
- Client-clip rows → running order only, no card. Test in Task 1.

---

### Task 1: `prompt_sheet.py` renderer

**Files:**
- Create: `.claude/edit-mo-to/tools/prompt_sheet.py`
- Test: `.claude/edit-mo-to/tools/tests/test_prompt_sheet.py`

**Interfaces:**
- Produces: `collect(folder: Path, specs: list[Path], script_lines: list[str], timings: dict|None) -> dict` (sections data: `characters`, `keyframes`, `groups` [{title, cards}], `order`, `setup`); `render(data: dict, title: str, job: str) -> str` (HTML); CLI `prompt_sheet.py "<folder>" [--prompts p.json ...] [--script s.txt] [--timings vo.json] [--title T] [--out html]` (default out `{tmp}/reports/<folder name>/prompt_sheet.html`), prints the out path.

- [ ] Step 1: tests — `test_clip_copy_matches_block` (card `copy` == `pt._block`), `test_storyboard_cards` (CHAR + SB cards, null prompt skipped, `waiting_keyframes` true), `test_client_rows_only_in_order`, `test_two_specs_two_groups`, `test_script_tag_escaped` (`"</script>"` in a prompt → HTML contains no second `</script>` before the end), `test_nothing_to_show_exits_2`.
- [ ] Step 2: run `pytest tests/test_prompt_sheet.py -q` → FAIL (no module).
- [ ] Step 3: implement; embed data as `json.dumps(...).replace("<", "\\u003c")`.
- [ ] Step 4: run tests → PASS; full suite `pytest -q -m "not slow"` stays green.
- [ ] Step 5: commit `feat(tools): prompt sheet page for copy-paste prompts`.

### Task 2: Workflow wiring

**Files:**
- Modify: `.claude/skills/edit-mo-to/SKILL.md` (Rules "Keep agent output small", step 4 storyboard bullets, step 6, tools list)
- Modify: `.claude/skills/edit-mo-to/reference/steps.md` (flag rewrite: re-render + republish)
- Modify: `.claude/edit-mo-to/style-agent-contract.md` (storyboard "word for word as pasted in chat", final-message line)
- Modify: `.claude/skills/practice-muna/SKILL.md` if it repeats the paste rule

- [ ] Step 1: replace "paste every prompt in chat" with: run `prompt_sheet.py`, publish with the Artifact tool (URL saved to `<folder>/.edit-mo-to/sheet_url`, reused as `url` later; no Artifact tool → open the local HTML), chat shows the table + link only.
- [ ] Step 2: `grep -rn "in chat" ` on those files shows no remaining prompt-paste rule; `pytest tests/test_gui_docs.py -q` PASS.
- [ ] Step 3: commit `docs(edit-mo-to): prompts live in the prompt sheet, not chat`.

### Task 3: Real-job check
- [ ] Render `Headlight Glasses Pixar` (storyboard + `HeadlightGlasses/prompts2.json`), publish, check copy/Done/dark mode in the browser pane.
