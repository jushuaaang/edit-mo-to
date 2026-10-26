# Brief Questions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Step 2 of /edit-mo-to asks up to 6 questions about unclear, implied, conflicting or missing brief rules at its existing gate, and records the answers as checklist rows.

**Architecture:** Instruction-only change to the skill text; no tool code.

**Tech Stack:** Markdown skill files.

**Spec:** `docs/superpowers/specs/2026-10-26-brief-questions-design.md`

## Global Constraints

- The gate count (⛔) in `.claude/skills/edit-mo-to/SKILL.md` (26) and `reference/steps.md` (2) stays the same; no new gate.
- Existing gate sentences stay word for word; the questions block is added after the Checklist gate sentence.
- At most 6 questions; answers become checklist rows with source `editor, <date>`; nothing written to `clients/`.

## Review Focus

- A clear brief: the gate must say "No questions about the brief." and behave as today.
- A rule that conflicts with `my-preferences.md`: it is asked about (the brief still wins by default).

---

### Task 1: Brief questions at the step 2 gate

**Files:**
- Modify: `.claude/skills/edit-mo-to/SKILL.md` (step 2 bullets, before the "⛔ Show the checklist" bullet)
- Modify: `.claude/skills/edit-mo-to/reference/steps.md` ("Reading briefs (step 2)" section: add a "Questions about the brief" bullet after "Checklist format"; "Gate wording" Checklist line: append the questions block wording)

- [ ] **Step 1:** In SKILL.md step 2, add one bullet: mark unclear / implied / conflicting (incl. with preferences) / missing (length, ratio, music, CTA, on-screen text) rules; at the checklist gate add "Questions about the brief" (≤ 6, most important first, one line each on what it changes); answers become checklist rows `editor, <date>`; clear brief → "No questions about the brief."; not saved to client notes.
- [ ] **Step 2:** In steps.md add the matching detail and the Checklist gate addition: after the existing sentence, "Questions about the brief:" followed by the numbered questions.
- [ ] **Step 3: Verify** `grep -o "⛔" .claude/skills/edit-mo-to/SKILL.md | wc -l` → 26 and same command on `reference/steps.md` → 2; `git diff` shows no removed gate sentence.
- [ ] **Step 4: Commit**

```bash
git add .claude/skills/edit-mo-to/SKILL.md .claude/skills/edit-mo-to/reference/steps.md docs/superpowers/specs/2026-10-26-brief-questions-design.md docs/superpowers/plans/2026-10-26-brief-questions.md
git commit -m "edit-mo-to: ask about unclear brief rules at the checklist gate"
```
