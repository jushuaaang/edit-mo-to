# Drama agent (`drama`) — design

Date: 2026-11-25 · Status: waiting for the editor's approval

## Why
Realistic drama ads (two people acting a scripted scene, each speaking their own lines in Google Flow clips) currently run through the `ugc` agent, which was built for selfie hosts. Headlight Drama needed 10 revision rounds and Petrol Station 8; the rules those rounds produced live in job notes, not in the workflow. The editor also brought a set of "good drama ad" criteria (hook, pacing, J/L cuts, shot progression, safe zones, mix, captions). One `drama` agent should follow all of this from the first draft, for both realistic and cartoon dramas.

## Goals
- One style agent, `drama`, with a **look switch**: `realistic` | `cartoon`. It replaces `cartoon-drama`.
- First drafts that already meet the editor's drama rules and the criteria below, so revision rounds are about taste, not repeat mistakes.
- Learned drama rules land in one place the editor can read and edit.

## Non-goals / anti-goals
- No new words in the script. Lines stay word for word; hooks follow the brief (see Rules).
- No zoom-ins or punch-ins. No speed ramps, freeze holds, slow-mo fixes or audio offsets (`audio_lead`) on clip-voice jobs.
- No music before step 11. No textless copy unless the brief asks.
- Don't break jobs in progress (Keeps AC90LAT uses `cartoon-drama`).

## Approaches
- **A. Rules in the agent file** (like today's `cartoon-drama.md`): all in one place, but learned rules go to `my-preferences.md` and drift from the agent; the agent file becomes long and unedited.
- **B. Rules in `preferences.md`, agent holds the method** (like `ugc`, `pixar`, `claymation`). **Chosen by the editor.** The learning step already writes to the matching section in `my-preferences.md`, so new lessons sit next to the rules they change.

## Rules (decided by the editor)
Shared (both looks):
- Script is law: every line word for word, in order, by its character. The reference gives pacing and energy, never its shots.
- **Hooks follow the brief:** hook versions only if the brief asks, made the way it says; otherwise one hook. Open in the middle of the conflict / sharpest line the script allows.
- **Shots:** ~1.5–3 s; a visual change every 3–5 s by **angle, shot size or listener reaction — never a zoom**. Wider at setup, tighter close-ups as tension rises. Speaker looks at the other person, never at camera (only the CTA lines may look to camera).
- **J/L cuts by reaction overlays:** the listener's silent reaction (mouth closed) is laid muted over part of the speaker's line; the voice always comes from its own clip, so lips never drift. Reaction clips are planned in the storyboard.
- **Location: strict unless the script moves:** one spot per scene, each person keeps their side of frame and the same background behind them; a new location only when the script changes scene.
- **Colour follows each scene's mood** (e.g. cooler/tenser in the conflict, warmer at the resolution), one grade per scene, natural skin.
- Pacing: pauses over 0.3 s cut to ~0.15 s (lead ~0.1 s, tail ~0.15 s); filler/stutter scan per line before review (existing my-preferences rules).
- Product as the turning point / resolution, not an interruption.
- Safe zones: faces, key action and graphics inside the 9:16 centre safe area (clear of the right-side icons, top tabs and caption band).
- Mix: clear, forward dialogue; light SFX (room tone, risers, impacts, script actions). Music: none until step 11; if added there, low and ducked under voices.
- Captions at step 10 as now; textless twin timeline only if the brief asks.
- Storyboard (keyframes) approved by the editor before any clip is generated; Flow x1; regenerate a bad take rather than fix it in the edit.

Realistic look (from Headlight Drama / Petrol Station):
- Both people in every medium and wide shot; close-ups are true close-ups of the speaker looking off-camera at the other person, attaching only that person's character sheet, with that person's fixed background plate.
- No over-the-shoulder shots with a back in the foreground.
- Voice lock per character written as text in the prompt (age, accent, pitch, tone, pace); clip's own audio, 1.0x, `audio_lead` 0.
- Ultra-realistic phone/cinema look per the brief; no text in frame.

Cartoon look: today's `cartoon-drama.md` rules and the `## Cartoon drama` preferences section, moved over unchanged (letterbox panel, 16:9 clips, style ref board, face/hair/head locks, set locks).

## What changes (files)
- `.claude/agents/drama.md` — new, short (like `ugc.md`): read contract + pack; modes storyboard / prompts / edit-plan; `"style": "drama"` with `"look"`; how reaction overlays, the cartoon panel build and voice locks are written.
- `.claude/agents/cartoon-drama.md` — deleted (never committed).
- `.claude/edit-mo-to/preferences.md` — `## Cartoon drama` becomes `## Drama` with shared rules + *Realistic* and *Cartoon* parts.
- `.claude/edit-mo-to/my-preferences.md` — the two drama lines stay in General (pacing, filler scan); the "115% punch-in" clause is removed (no zooms now wins).
- `tools/context_pack.py` — `drama` → `Drama` section; `cartoon-drama` kept as an alias to the same section.
- `tools/plan_tools.py` — `drama` in `REQUIRED_LOCKS`, look-dependent: realistic = `realism, notext, voice, look, pacing`; cartoon = `style_bible, notext, voice, look, pacing`. `cartoon-drama` kept as an alias for `drama` + cartoon. Tests in `tools/tests/test_plan_tools_prompts.py`.
- `style-agent-contract.md`, `skills/edit-mo-to/SKILL.md`, `reference/steps.md` — list `drama` instead of `cartoon-drama`; routing line: "Drama acted by characters speaking their own lines (live-action or cartoon) → `drama` (look: realistic | cartoon)".

## Left to the builder
Exact wording of the agent and preference text; how `look` is passed (`prompts2.json` / `plan2.json` field, default `realistic`); the test cases.
