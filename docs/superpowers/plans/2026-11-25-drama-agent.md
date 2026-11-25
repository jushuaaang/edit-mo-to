# Drama agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One `drama` style agent (look: realistic | cartoon) replaces `cartoon-drama`, with its rules in `preferences.md`.

**Architecture:** Rules live in a `## Drama` section of `preferences.md` (context_pack delivers it); `.claude/agents/drama.md` holds only the method. `plan_tools.py` checks drama locks per look; `cartoon-drama` stays as an alias so jobs in progress still check.

**Tech Stack:** Python 3 (tools), pytest, Markdown (agents, preferences, skill docs).

**Spec:** `docs/superpowers/specs/2026-11-25-drama-agent-design.md`

## Global Constraints
- Style key `drama`; look field `"look": "realistic" | "cartoon"` in `prompts2.json` / `plan2.json`, default `realistic`.
- Locks: realistic = `realism, notext, voice, look, pacing`; cartoon = `style_bible, notext, voice, look, pacing` (images drop voice, pacing as today).
- `cartoon-drama` = alias of `drama` + look `cartoon` (plan_tools and context_pack).
- No zoom-ins; no `audio_lead` on clip-voice jobs; music none until step 11; textless twin only if the brief asks; hooks follow the brief.
- Never commit `my-preferences.md`; nothing is committed unless the editor asks.

## Review Focus
- An old `prompts2.json` with `"style": "cartoon-drama"` (Keeps AC90LAT) must still pass `check-prompts` with the cartoon locks → test in Task 1.
- A drama spec with no `look` must be checked as realistic, not error → test in Task 1.
- A typo look (`"look": "anime"`) must give a clear "unknown look" error, not a KeyError → test in Task 1.
- `context_pack.py drama` and `context_pack.py cartoon-drama` both pick the `## Drama` section → test in Task 1.
- Cartoon keyframes still need no voice/pacing lock → test in Task 1.

---

### Task 1: Tools know the `drama` style

**Files:**
- Modify: `.claude/edit-mo-to/tools/plan_tools.py` (REQUIRED_LOCKS ~473, check_prompts ~580)
- Modify: `.claude/edit-mo-to/tools/context_pack.py:20`
- Test: `tools/tests/test_plan_tools_prompts.py`, `tools/tests/test_context_pack.py`

**Interfaces:**
- Produces: `lock_style(spec: dict) -> str` in plan_tools (returns a REQUIRED_LOCKS key: `drama:realistic`, `drama:cartoon`, or the plain style); REQUIRED_LOCKS keys `drama:realistic`, `drama:cartoon`; `cartoon-drama` maps to `drama:cartoon`. context_pack STYLES gains `drama: "Drama"`, `cartoon-drama: "Drama"`.

- [ ] **Step 1: Failing tests** — `test_drama_realistic_locks` (style drama, no look, video prompt with ugc locks minus product passes; missing `realism` errors), `test_drama_cartoon_and_old_alias` (style drama+look cartoon and style cartoon-drama both need `style_bible`; keyframe without voice/pacing passes), `test_drama_unknown_look` (look anime → error containing "unknown look"), `test_pack_drama_and_alias_use_drama_section` (PREFS fixture gets `## Drama\ndrama rule`; both styles' pack contains "drama rule").
- [ ] **Step 2: Run** `"{python}" -m pytest tools/tests/test_plan_tools_prompts.py tools/tests/test_context_pack.py -q` → new tests FAIL.
- [ ] **Step 3: Implement** `lock_style` and use it in `check_prompts` (unknown look → `unknown look {look!r} for drama (realistic or cartoon)`); update STYLES.
- [ ] **Step 4: Run** same command → all PASS.

### Task 2: Rules and agent

**Files:**
- Modify: `.claude/edit-mo-to/preferences.md` (`## Cartoon drama` → `## Drama` with shared, *Realistic*, *Cartoon* parts, per the spec's Rules)
- Modify: `.claude/edit-mo-to/my-preferences.md` (drop the "115% punch-in" clause only; local, not committed)
- Create: `.claude/agents/drama.md` (short, like `ugc.md`: contract + pack, modes storyboard/prompts/edit-plan, `"style": "drama"` + `"look"`, reaction overlays, voice locks, cartoon panel method moved from `cartoon-drama.md`)
- Delete: `.claude/agents/cartoon-drama.md`

- [ ] **Step 1:** Write the files. **Step 2:** `context_pack.py drama` on this repo prints the Drama section (check by eye).

### Task 3: Routing and docs

**Files:** `.claude/edit-mo-to/style-agent-contract.md` (lines 1, 78), `.claude/skills/edit-mo-to/SKILL.md` (lines 8, 39), `.claude/skills/edit-mo-to/reference/steps.md:20`

- [ ] **Step 1:** Replace `cartoon-drama` with `drama`; steps.md line: "Drama acted by characters speaking their own lines (live-action or cartoon) → `drama` (look: realistic | cartoon)".
- [ ] **Step 2:** `grep -rn cartoon-drama .claude` → only the alias lines in tools and the alias note.
- [ ] **Step 3:** Full test run `"{python}" -m pytest tools/tests -q` → PASS.
