# Prompt sheet artifact — design (approved 2026-11-19)

## Why
Editors struggle to copy generation prompts out of chat, `.txt` or `.md`. They asked for an organised page
(concept: the "Courtroom Clip Sheet" artifact) where every prompt is a card with a Copy button.

## Goals
- Every generation prompt of a job (character sheets, storyboard keyframes, clip prompts) lives in one
  prompt sheet page, one card per prompt, with Copy prompt, Done tick and Show prompt.
- The page is published as an Artifact; the link stays the same for the whole job.
- Chat shows the shot table and the sheet link only — **no prompt text in chat**.

## Non-goals / anti-goals
- Not a replacement for the GUI app (it keeps its own Copy).
- Copy must never give text different from what the checks passed (`prompts.txt` / `storyboard.json`).
- Claude never hand-writes the sheet HTML per job.

## Approaches
1. **Renderer tool (picked):** `tools/prompt_sheet.py` builds the page from `storyboard.json` + `prompts2.json`.
   Same text as the checked prompts, same look every job, cheap.
2. Claude writes the HTML each job: flexible but costly, drifts from the checked prompts, inconsistent.
3. GUI-only Copy: doesn't help chat users.

## Design
- `prompt_sheet.py "<video folder>" [--prompts <prompts2.json> ...] [--script s.txt] [--timings vo.json] [--title T] --out <html>`.
  Reads `<folder>/storyboard/storyboard.json` when present; any number of prompts2 specs (one per timeline).
- Sections (only those with content): Setup (generator, attach list, notes) → Characters → Keyframes → Clips
  (one group per spec/timeline) → Running order.
- Card: plain id ("Shot 3 (SB-3)"), script line, VO in/out in `seconds:frames`, length (+gen length), generator,
  attach chips, "Save as", note chip (e.g. "rewritten after a flag"), Copy prompt, Done (localStorage, keyed by job),
  Show prompt. Copy text = `plan_tools._block` (clips) or the beat/character `prompt` (storyboard).
- Client clips: running order rows only (file + cut), no card.
- Self-contained HTML, light/dark, phone width, clipboard fallback selects the text.
- Publishing: Claude publishes with the Artifact tool; the URL goes in `<folder>/.edit-mo-to/sheet_url` so a later
  session republishes to the same link (`url`). No Artifact tool: open the local HTML instead.
- Re-render + republish whenever prompts change (new phase, fix, flag rewrite).
- Rules in SKILL.md, `reference/steps.md`, `style-agent-contract.md` change from "paste every prompt in chat" to
  "shot table + sheet link". QA still reads `prompts.txt`.

## Left to the builder
Visual styling, exact chip set, file layout inside the tool.
