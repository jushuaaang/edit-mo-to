# edit-mo-to: Design

## Intent

The user is a video editor making client ads: UGC selfie reviews, B-roll ads, claymation, Pixar-style animation and TikTok product ads. Today Claude writes scripts and prompts, the user generates the clips (Google Flow, Seedance), voiceover (ElevenLabs) and music (Suno or no-copyright YouTube), and then does the whole edit by hand in CapCut.

A CapCut MCP server is now installed. edit-mo-to is the user's own end-to-end workflow, built so that Claude follows the client's brief exactly, drives the user through each step, and **builds the CapCut project itself**. The user then reviews it, chooses who adds the captions (CapCut auto-caption, or Claude's text captions), picks the music and exports.

The system should get better at working "just like the user" after every video.

## Goals

- One command, `/edit-mo-to`, that runs the user's 12-step process (below) in order and stops at every point where the user must act or decide.
- Follow the client's brief to the letter. Every rule in the brief is extracted, tracked, and checked by QA.
- Produce a CapCut project, named after the product, that is ready to review: clips in order and timed to the voiceover (or to music for product ads), with sensible transitions and effects.
- Learn from each video: what the user corrected becomes a saved preference, and agents are updated.

## Non-goals

- Captions before step 10. Never add caption or subtitle tracks before step 10, except the `TEMP_EN_delete_me` review track (temporary English lines for a script that is not English or Filipino, deleted by the user before export); at step 10 the editor chooses. Word-by-word animated captions are out of scope (CapCut's caption presets do that). Design: `docs/superpowers/specs/2026-10-26-captions-design.md`.
- Exporting or rendering the final video.
- Generating clips, voiceover or music. Claude writes prompts; the user generates.
- Replacing `/ugc` in `PYNK_AI_UGC_Studio`. It stays as it is.

## Anti-goals (failure even if it "works")

- Ignoring or loosely following a rule from the client brief.
- Moving on without the user's go-ahead at a gated step, or guessing at a choice the process says to ask about (B-roll source, generator, music source, script approval).
- Reusing the same clip twice in an edit, or slow, repetitive cutting.
- Writing deliverables as .md files when the user wants them in chat. Clip lists, prompts and edit plans go **in chat as tables**. The workflow's own config and memory files are fine.

## Location and layout

Everything lives in `D:\Video Editing\` (the user's call), not in `PYNK_AI_UGC_Studio`. Sessions for edit-mo-to are opened in `D:\Video Editing`.

```
D:\Video Editing\
  CLAUDE.md                      short: edit-mo-to is the main workflow; points to preferences file
  .claude\
    skills\edit-mo-to\SKILL.md       the orchestrator (the 12 steps)
    skills\edit-mo-to\reference\     supporting docs the skill loads on demand
    agents\                      the subagents (below)
    edit-mo-to\preferences.md        learned preferences, seeded from past sessions
    edit-mo-to\clients\<client>.md   per-client notes (brief rules, what they liked)
  <Client or Product>\           per-video folder the USER creates at the start
                                 (raw/downloaded B-roll, generated clips, VO, music)
  docs\edit-mo-to-design.md          this document
```

The per-video folder is created by the user. edit-mo-to asks for its path at step 1.

## The process (the user's 12 steps, as decided)

1. **Brief.** Ask for the client's brief or instructions: PDF, .docx, Notion URL, or pasted in chat. Also ask for reference videos. Notion: public pages only (connector not authorized); if a page can't be read, ask the user to paste or export it.
2. **Study the brief.** Read everything carefully. Produce a **brief checklist**: every rule, requirement, do and don't, length, aspect ratio, tone, CTA, required shots and banned content, each quoted from the source. Study reference videos if given (extract frames and audio with ffmpeg, transcribe with Whisper). Show the checklist to the user. Pick the style (UGC, B-roll, claymation, Pixar, product ad) from the brief, or ask.
3. **Script.** If the brief contains a script, use it verbatim. If not, ask questions, write one, and **wait for the user's approval**. TikTok product ads have no script; they are cut to music (see the "TikTok video editing with Notion" session for the pattern).
4. **Voiceover.** If a VO is needed, wait for the user to generate it in ElevenLabs and attach it.
5. **VO timing.** Transcribe the VO (faster-whisper, word timestamps) to get the exact start and end of each script line, in CapCut `seconds:frames`.
6. **B-roll.** Ask: use the client's B-roll, generate AI video, or both? If generating, ask: **Higgsfield or Google Flow?** and, for Higgsfield, **which model?** (Higgsfield replaced Seedance as a generator choice on 2026-10-28; Seedance is now a Higgsfield model, and each generator's limits live in `.claude/edit-mo-to/generators.json`.) Then:
   - Client B-roll: catalogue it (ffprobe for duration and fps, frame grabs to see content) and map clips to script lines.
   - AI: write one prompt per script line or beat, sized to that line's VO duration, following that generator's rules (see Style agents).
   Present as a chat table: line, timing, source (client file path or prompt), clip length.
7. **Gather and build.** If AI clips were needed, wait until the user attaches or drops them in the video folder. Then build the CapCut project, named after the product.
   - **Hooks become timelines (user's decision).** When a video has several hooks, it is still **one project**. Timeline 01 holds the body and CTA. Timeline 02 holds Hook 1, Timeline 03 holds Hook 2, and so on.
   - Each timeline is built as its own draft and then composed into one project (see Constraints).
   - Timelines are named "Timeline 01 – Body+CTA", "Timeline 02 – Hook 1", and so on (builder may shorten).
8. **Transitions and effects.** Added where they fit the style.
9. **Review loop.** The user reviews in CapCut, then either edits it themselves or tells Claude what to change. Repeat as needed. **Changes stay in the same project, never a v2 project (user's decision).** Before working, Claude asks two things: which timeline the changes are for, and whether to:
   - **(a) make a new timeline:** add one (e.g. "Timeline 05 – Hook 1 rev 1"), starting from that timeline with the changes applied. Other timelines are not touched.
   - **(b) work directly in that timeline:** apply the changes in place. Claude's call: first back up that timeline's folder (e.g. `Timelines\<id>.bak-<date>`) so it can be restored.
   - Adding a timeline means writing into the project folder (`Timelines\project.json` plus a new `Timelines\<id>\`), so Claude asks the user to close the project in CapCut first. Otherwise CapCut may overwrite the change.
   - Claude's call: if a hand-edited timeline can't be safely copied and patched for a given change, Claude rebuilds that timeline from its edit plan plus the changes, and tells the user which hand edits they'll need to redo.
10. **Captions.** The editor chooses: "Captions: will you run CapCut auto-caption yourself, or should I add them? (Mine are simple text captions with the script's exact words and a pop-in; no word-by-word animation. For an animated look, use CapCut's caption presets.)" Auto-caption: edit-mo-to waits until it's done. Claude's captions: the editor agent's `add-captions` runs the hand-edit diff, then `build_project.py captions` (script words timed by the VO, mapped through the timeline's live VO segments, chunked 2–4 words, merged as a `captions` text track without touching hand edits), then `qa_check.py captions` (words = script, sync to the VO, caption band, gaps).
   - **Temporary English (TEMP_EN):** a script that is not English or Filipino gets a literal English line per script line, written at step 3 next to the script (`script_en.txt`), shown from the first build on a top-of-frame `TEMP_EN_delete_me` track so the editor and QA can follow the meaning. The job card says "TEMP_EN on: delete before export"; the step-12 hand-off starts with "Delete the TEMP_EN_delete_me track before export". Removal is tracked per timeline: a cleared timeline's `temp_en_removed` keeps later builds of it from adding the track back, the job card lists "TEMP_EN still on: <timelines>", the plan-wide flag is set only when every timeline is clear, and the step-12 reminder comes from a fresh `capcut_project.py segments` check of every timeline. The deletion is never learned as a hand edit.
11. **Music.** Ask: a Suno prompt from Claude, or the user finds no-copyright YouTube music? Write the Suno prompt if chosen. When the user provides the music file, add it to the project at a level under the VO.
12. **Export.** The user does it. edit-mo-to ends with the **learning step** (below).

## Agents

The `/edit-mo-to` skill runs in the main conversation and owns all talking to the user, because subagents can't pause to ask questions. It sends heavy, self-contained work to these agents.

**Style agents (5): `ugc`, `broll`, `claymation`, `pixar`, `product-ad`.** Each knows its style's rules, drawn from the user's past sessions, and its section of `preferences.md`. Given the brief checklist, script, VO timings and clip inventory (as paths: a context pack written once per job by `context_pack.py`, the `media_timing.py vo` JSON plus its `--compact` text, `limits.json`, and a `sheets.py inventory` of the client's B-roll), each produces, as compact specs that `plan_tools.py` expands and checks (`prompts2.json` → `prompts.txt`, `plan2.json` → `plan.json` + `plan_table.txt`):
- B-roll / AI video prompts (step 6), with the user's must-repeat blocks in every prompt: style bible, product lock, realism line, which reference image to attach, "no subtitles / no on-screen text."
- An **edit plan**: an ordered timeline table (track, file path, source in/out, timeline start/end, speed, position/scale for split screens and grids, transition, effect, script line covered).

Style rules to seed them with:
- **UGC:** hooks (H1–H4 variants), then body, then CTA. Clips 4–8s, 30–40 clips for longer ads. Host A-roll lip-synced to the ElevenLabs VO, B-roll covering VO. Speed tweaks for lip-sync (see `lipsync_report.md`). The `/ugc` skill's 4-beat, 15s structure applies to short selfie reviews.
- **B-roll:** cut every 1.5–2s, 4s max per clip, never reuse a clip, top/bottom split screens (before/after, macro over live) and 2×2 / 3×3 grids.
- **Claymation:** each clip timed to a pre-split audio slice (`H1.mp3`, `B1.mp3`…). Style and audio block in every prompt. Fixed voice tone per character. Single-character shots for dialogue.
- **Pixar:** keyframe images S1–Sn, then clips C1–Cn (generated 5–8s, used 2.5–8s), 30–45s total. Style bible at the end of every prompt. VO, music and SFX hits.
- **Product ad:** 10–20s, cut to music, 2–4s clips from different angles, logo in one clip, image-first then image-to-video in Flow.

**Editor agent (`editor`).** The only agent that touches CapCut, now a thin runner (`model: sonnet`). Takes an approved edit plan and builds the whole project in one `build_project.py build` run through the VectCutAPI backend: overlays rendered in parallel, one draft per timeline (**9:16 by default, the user's standard**: 1080×1920, 30 fps, unless the brief says otherwise) with video, audio, text (badges and CTA graphics, plus the `TEMP_EN_delete_me` review track on non-English, non-Filipino jobs; never captions at build time), keyframes, effects and transitions, composed into one project in CapCut's drafts folder (`{capcut_drafts}`) under the product name, with the user's files imported and a frame sheet per timeline. Applies review-loop changes as a new timeline (`build_project.py timeline` + `add-timeline`) or in place (`plan_tools.py ops` → `capcut_project.py patch`, or `replace` for layout changes), always after `edit_diff.py diff --last` reports the user's hand edits; adds Claude's captions at step 10 when the editor chooses them (`build_project.py captions`, merged with `add-tracks … text`); adds music after captions with `build_project.py music` + `add-tracks`. Reports what it built plus anything it could not do (e.g. mirroring, unmapped patch rows) so the user can do it by hand.

**QA agent (`qa`).** Read-only checker. Runs at four gates and returns a pass/fail table with specific fixes. The checks that need no eyes run as scripts first (`qa_check.py prompts`, `qa_check.py build` and `qa_check.py captions`, FAIL and OPEN rows only, `--changed` for a delta); the agent then judges only what needs reading or looking, from tiled frame sheets (`sheets.py`) instead of single frames:
- After the script (step 3): does the script follow every brief-checklist item?
- After prompts / B-roll mapping (step 6): does each line's visual fit its script line and the brief?
- After the build (step 7, and after each review-loop change):
  - Each clip matches the line it covers (judged from the clip sheets; AI clips in/mid/out; overlays composited on the A-roll under them).
  - Timing is in sync with the VO.
  - No clip is reused.
  - Total length, aspect ratio and required elements (CTA, logo, badges) are present.
  - Nothing from the brief is missed.
- After Claude's captions (step 10, when the editor chose them): `qa_check.py captions` per timeline checks the `captions` track's words against the script (minus words of a cut VO stretch, listed as OPEN), each chunk's sync to its words (±2 frames), the caption band and gaps over 0.5 s in speech; TEMP_EN shows as an OPEN reminder. The agent judges only FAILs that need eyes and the brief's caption rules.

  edit-mo-to doesn't show the user a build until QA passes, or until QA's remaining issues are listed for the user.

## Learning ("work just like me")

- `preferences.md` is seeded at build time from the 10 past sessions reviewed. Highlights:
  - timecodes in `seconds:frames`
  - full file paths
  - tables in chat, no .md deliverables
  - fast, varied cuts with no repeats
  - short clips
  - the must-repeat prompt blocks
  - known generation failures to prevent (label/text drift, colour and skin-tone shifts, blur, lip-sync stutter, extra hands, mispronunciations)
  - Google Flow takes at most 7 attachments
- The **learning step** (end of every video): compare the user's review-loop requests and any manual edits they describe, propose additions to `preferences.md`, the matching style agent, and `clients/<client>.md`, and apply them after the user OKs them.
- `PYNK_AI_UGC_Studio`'s "keep no memory" rule does not apply to edit-mo-to.

## Constraints

- CapCut MCP server (`capcut`, user-scoped) plus the VectCutAPI backend, which auto-starts. Supported: draft size and fps, video (timing, speed, transitions), audio (volume, fades), text (font, colour, background box, animation), effects, keyframes, position, scale and rotation, save draft with a name. Mirroring is not visibly supported; treat it as manual unless the builder finds a way.
- **Verified on CapCut 9.6 (2026-10-15):** a VectCutAPI draft (`capcut_legacy` profile, `draft_info.json`) saved into the drafts folder opens and plays, with text. A **multi-timeline** project also opens correctly. It was composed by script from two separately built drafts into the native layout: `Timelines\project.json` (timeline list + `main_timeline_id`) plus `Timelines\<id>\draft_info.json` and `draft_content.json` per timeline, the root `draft_info.json` equal to the main timeline, shared `assets\`, and `draft_meta_info.json` updated. The spike scripts are `C:\Users\Keytech\mcp-servers\tmp\compose.py` and `fixpaths.py`; turn them into one proper tool. Gotchas found:
  - Every VectCutAPI draft has the same timeline id, so each timeline needs a fresh UUID.
  - Media paths are absolute, with mixed `/` and `\`, pointing into the source draft's `assets\`. Rewrite them to the final project's `assets\`.
  - `save_draft` reports success even when it fails (e.g. a path too long for Windows). Always check the output folder exists, and build in a short path such as `C:\Users\Keytech\mcp-servers\tmp`.
  - Saves are asynchronous. Wait for the folder to appear.
  - VectCutAPI copies media into the draft's `assets\`, so projects take up disk space.
- **The backend only auto-starts when a session loads the CapCut MCP tools.** The editor must make sure it is up (port 9001) before calling it. On Windows it must run with `PYTHONIOENCODING=utf-8`: otherwise a draft with keyframes saves empty while VectCutAPI answers success, and `build_project.py` raises `DraftSaveFailed`.
- **Every write to a CapCut project goes through `capcut_project.py`** (compose, add-timeline, replace, patch, add-tracks, add-overlay); nothing hand-edits `draft_content.json`. Each write backs the timeline up and saves `<project>/edit-mo-to-backups/<timeline>.last.json`, so `edit_diff.py diff --last` shows only the user's hand edits.
- **Times inside the tools are whole frames at 30 fps or integer microseconds;** the contract plan carries seconds with 10 decimals, written by `plan_tools.py expand`, never by hand. The plan check (`plan_tools.py check`) must be clean before any build.
- Local tools: ffmpeg and ffprobe on PATH; Python 3.12; faster-whisper (used previously; confirm it is installed).
- Windows paths with spaces everywhere; quote them.

## Claude's calls (user may override)

- **Product ads pick music before the build.** They're cut to the beat, so step 11 (music choice) moves up to just before step 6 for product ads only. The user still chooses Suno or YouTube, and Claude detects beats with ffmpeg/librosa to time cuts. Other styles keep music at step 11.
- **No VO slicing (user's decision).** Claude does not split the voiceover into files. Instead, every AI-generation prompt is **timed exactly to the VO**:
  - its clip length equals the duration of the line(s) it covers, from the step 5 timings;
  - its spoken words (for lip-sync and claymation) are the exact script words, with their in/out times in `seconds:frames`;
  - each prompt row in the chat table shows VO in → out next to the prompt.
- **Seed sources.** Past transcripts are in `C:\Users\Keytech\.claude\projects\D--Video-Editing-PYNK-AI-UGC-Studio\` (and `...-clipper-1-0-0-tar\`). Mine these when writing `preferences.md` and the style agents, especially "TikTok video editing with Notion" (product-ad / music-only pattern, CapCut `seconds:frames` timelines, "mirror every clip"), "Nativia UGC ads production" (lip-sync), "Claymation style ads", "NorthPower Pixar-style ad", "Zapply script body with B-roll" and "B-roll video creation". Also use `D:\Video Editing\PYNK_AI_UGC_Studio\lipsync_report.md` and the `/ugc` skill.
- **The old `PYNK_AI_UGC_Studio` setup is left untouched.** Its CLAUDE.md rules don't apply in `D:\Video Editing`. The new `D:\Video Editing\CLAUDE.md` must not tell Claude to auto-run `/ugc`.
- **Every project defaults to 9:16 (user's decision).** Prompts ask for 9:16, drafts are 1080×1920, and a different ratio is used only when the brief asks for it.
- **Clean up the test projects.** Once real projects work, delete "g-pare test" and "g-pare timelines test" from CapCut's drafts folder, after asking the user.

## Left to the builder

- Exact wording and structure of the skill and agent files, and how much reference material each loads.
- How QA judges "clip matches line" (frame sampling rate, etc.).
- Audio defaults: generated-clip audio muted under VO; lip-synced A-roll keeps VO only. Music around -18 to -20 dB under VO. Adjustable per brief.
- Which model each agent runs on.
