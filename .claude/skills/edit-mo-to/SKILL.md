---
name: edit-mo-to
description: The user's end-to-end client video workflow - from client brief to a finished CapCut project. Use when the user runs /edit-mo-to, starts a new client video or ad (UGC, B-roll, claymation, Pixar-style, product/TikTok ad), shares a client brief or trial instructions (PDF, docx, Notion link, pasted text), or wants a video edited/assembled in CapCut. Runs 12 gated steps, dispatches the style, editor and QA agents, and learns the user's preferences at the end.
---

# edit-mo-to

The user's own editing workflow. You run it in the main conversation and own all talk with the user. Agents do the heavy, self-contained work: `ugc`, `broll`, `claymation`, `pixar`, `product-ad` (style), `motion-designer` (new looks and templates only), `editor` (builds CapCut, renders overlays), `qa` (checks).

**Before step 1:**
- Resolve `{root}`, `{python}`, `{tmp}`, `{capcut_drafts}` from `.claude/edit-mo-to/machine.json` (see CLAUDE.md) and pass resolved paths to agents.
- Sync: `git -C "{root}" pull --ff-only` (brings in what the other PC learned). If it fails, say so and continue.
- Read `{root}/.claude/edit-mo-to/preferences.md` (General), then `clients/<client>.md` once you know the client, and `reference/steps.md` (gate wording, dispatch templates).

## Hard rules
- **STOP at every ⛔ gate.** Ask and wait; never assume a choice the process says to ask about. A gate the user already answered (in the brief message or earlier: folder, B-roll source, generator, music, VO file) is answered: confirm it in the job card and go on. Ask the remaining questions of a step together, not one per message.
- **Work in parallel where nothing depends on order:** independent agent runs (style agent per hook timeline, QA per timeline, `motion-designer` while prompts are written) go out in one message. Never parallel two `editor` runs on one project, or anything across a ⛔ gate.
- **The brief is law.** Every brief rule goes on the checklist, and QA checks it.
- CLAUDE.md's formats apply (chat tables, `seconds:frames`, full paths, 9:16, no captions, user exports). Prompts go in copyable code blocks.
- **Keep agent output small.** Agents hand back ~30 lines and leave full tables, prompts and plan JSON in `{tmp}/reports/<job>/`. Pass those paths on (style agent → editor and QA) instead of the content, and show the user the deliverable table from the file without re-summarising.
- **Re-runs post only what changed:** only the changed sentences of a fixed prompt (or the prompt file path), not the whole prompt and its locks. After a small fix run `qa` with `scope: delta` and `changed:`; a full QA run is for the first pass at each gate, or when QA says the change reaches further.
- **Job card:** keep a running card (client, product, style, video folder, brief checklist, script, VO path + timings, B-roll source, generator, music, project name, timelines). Re-show it when it changes.

## The 12 steps
1. ⛔ **Brief.** Ask for the brief (PDF, docx, Notion URL or pasted), reference videos, and the per-video folder under `{root}/`. If they came with the request, just confirm the folder exists and go on.
2. **Study the brief** (steps.md covers PDF, docx, Notion and video).
   - Build the **brief checklist**: every rule quoted with its source (length, ratio, tone, hook/CTA rules, must-show / never-show, claims, music and SFX, text style, export settings, deadline).
   - Study the reference videos (frames + transcript) and pick the style.
   - If the user or brief wants a reference's graphic look and `motion\CATALOGUE.md` has no match, dispatch `motion-designer` with the reference and a few client-footage frames. Its style spec and templates feed the style agent's plan.
   - ⛔ Show the checklist and style; ask the user to confirm or add.
3. **Script.**
   - Brief has a script: use it word for word.
   - No script: ⛔ ask your questions, write it, run `qa` (gate `script`), ⛔ wait for approval.
   - TikTok product ad: no script. **Music first:** ⛔ "Suno prompt or your own no-copyright YouTube music?", wait for the track, go to step 5 (beats).
4. ⛔ **Voiceover.** Wait for the user's ElevenLabs file. Note whether it's **one file** (hooks + body) or **one per hook/body**; it sets each timeline's `vo_in`/`vo_out`.
   - **Reusing an existing VO** (saves credits): `media_timing.py vo <file>` with no script, show its sentences with times, ⛔ let the user pick the spans. The script becomes those spoken lines; each timeline's `vo_in`/`vo_out` is its span.
5. **Timing.** VO: `media_timing.py vo <vo> <script.txt>` (script lines in a temp txt); show the line timings. Any `matched: false` line is a ⛔ check (mispronounced or changed words). Music (product ads): `media_timing.py beats <music>`.
   - **Talking-head A-roll with its own audio** (avatar, creator, host recording): clean it first. `speech_cuts.py propose <clip> --out {tmp}/cuts/<name>.cuts.json` (reuses the cached transcript) finds dead air (pauses over 0.55s trimmed to a breath; edges snapped to real silence) and stutters / false starts / retakes. Silence cuts apply automatically. ⛔ Show the mistakes as a table (`id | type | cut | removes | keeps | recommend`) and ask which to cut; emphasis ("never, never") looks like a stutter. Then `speech_cuts.py apply <cuts.json> --approve <ids> --reject <ids> --script <script.txt>`. Its `keep.json` (`segs`, re-timed `words` and `lines`) replaces the VO timings for that clip and goes to the style agent as `aroll_cuts`. Tighter pacing: `--gap 0.3 --breath 0.15`.
6. **B-roll and prompts.**
   - ⛔ "Use the client's B-roll, generate AI video, or both?" If AI: ⛔ "Where will you generate: Seedance or Google Flow?"
   - Dispatch the style agent (`mode: prompts`), then `qa` (gate `prompts`).
   - Show the table and prompts. Fix QA FAILs by re-dispatching (then delta `qa` on the fixed rows), or list unresolved ones for the user.
7. ⛔ **Gather and build.**
   - If AI clips are needed, wait until the user says where they are, then inventory them (ffprobe).
   - Dispatch the style agent (`mode: edit-plan`). Plan `overlays` use `motion\CATALOGUE.md` templates and the **editor renders them** during the build; only a graphic no template covers needs `motion-designer` first.
   - Dispatch `editor` (`action: build`, project name = product name, hooks as timelines, the plan, `import_files` = every file the user gave for this video). It imports them into the media panel and builds from the originals.
   - Run `qa` (gate `build`). If the project name is taken, ⛔ ask for another (e.g. "<Product> 2").
   - Show the editor's report and QA verdict. Send the user to CapCut only once QA passes, or with the remaining issues listed.
8. **Transitions and effects** are in the edit plan where they fit the style and brief.
9. ⛔ **Review loop.** The user reviews in CapCut and edits it themselves or gives changes. For each change, ⛔ ask which timeline, and new timeline or in place (in place makes a backup), and ⛔ ask them to quit CapCut completely (it rewrites projects on close and would drop our change; the tool refuses while CapCut.exe runs).
   - Then: style agent (`edit-plan` + `revision`), `editor` (`revise-new-timeline` | `revise-in-place`), `qa` (`build`, delta for small changes).
   - **Overlay tweaks** ("move the card up") stay in the main conversation: change the vars, re-render with `motion_render.py`, preview, then have the editor swap the files. No agent for small tweaks.
   - Repeat until the user is happy.
10. ⛔ **Captions.** Remind the user to run CapCut auto-caption; wait until done.
11. ⛔ **Music** (non-product-ad styles): "Suno prompt from me, or no-copyright YouTube music?"
    - Suno: write the prompt; max 18s, so split into parts with crossfade notes.
    - When the file arrives: ⛔ ask which timeline(s) and to quit CapCut, then `editor` `action: add-music`. It **merges** the music (about −20 dB under the VO), keeping captions and hand edits, with a backup.
12. **Export** is the user's. Then run the **learning step** (`reference/learning.md`).

## Tools
- Python: `"{python}"`; tools in `{root}/.claude/edit-mo-to/tools/`:
  - `media_timing.py`: `vo <audio> [script.txt]`, `beats <audio>`
  - `speech_cuts.py`: `propose <clip>`, `apply <cuts.json>` (dead air and mistake cuts, step 5)
  - `edit_diff.py`: `snapshot` (editor, after builds), `diff` and `history` (learning step: what the editor changed by hand)
  - `capcut_project.py`: `list <project>` (show timelines); the editor uses the rest.
  - `motion_render.py`: `list`, `render <template> <out.mov> --vars-file f.json`, `preview <mov> <png>`. Catalogue: `motion/CATALOGUE.md`.
  - `plan_preview.py <plan.json> <out.mp4>`: ffmpeg preview of a frame-based plan with overlays.
  - `playbook_scan.py <slug> <folderToken> <outdir>`: contact sheets of a shared Playbook folder without downloading. Its organization header is exchange-life; change it for other clients.
- ffmpeg and ffprobe are on PATH. Temp files go in `{tmp}/` (short path).
