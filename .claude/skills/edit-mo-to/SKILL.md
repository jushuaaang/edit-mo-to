---
name: edit-mo-to
description: The user's end-to-end client video workflow - from client brief to a finished CapCut project. Use when the user runs /edit-mo-to, starts a new client video or ad (UGC, B-roll, claymation, Pixar-style, product/TikTok ad), shares a client brief or trial instructions (PDF, docx, Notion link, pasted text), or wants a video edited/assembled in CapCut. Runs 12 gated steps, dispatches the style, editor and QA agents, and learns the user's preferences at the end.
---

# edit-mo-to

The user's own editing workflow. You run it in the main conversation and own all talk with the user. Agents do the heavy, self-contained work: `ugc`, `broll`, `claymation`, `pixar`, `product-ad` (style), `motion-designer` (new looks and templates only), `editor` (builds CapCut, renders overlays), `qa` (checks).

**Before step 1:**
- Resolve `{root}`, `{python}`, `{tmp}`, `{capcut_drafts}` from `.claude/edit-mo-to/machine.json` (see CLAUDE.md) and pass resolved paths to agents.
- Read `{root}/.claude/edit-mo-to/preferences.md` (General) and `my-preferences.md` if it exists (the editor's own rules; it wins on conflict), then `clients/<client>.md` once you know the client, and `reference/steps.md` (gate wording, dispatch templates).

## Hard rules
- **STOP at every ⛔ gate.** Ask and wait; never assume a choice the process says to ask about. A gate the user already answered (in the brief message or earlier: folder, B-roll source, generator, music, VO file) is answered: confirm it in the job card and go on. Ask the remaining questions of a step together, not one per message.
- **Work in parallel where nothing depends on order:** independent agent runs (style agent per hook timeline, QA per timeline, `motion-designer` while prompts are written) go out in one message. Never parallel two `editor` runs on one project, or anything across a ⛔ gate.
- **The brief is law.** Every brief rule goes on the checklist, and QA checks it.
- CLAUDE.md's formats apply (chat tables, `seconds:frames`, full paths, 9:16, no captions, user exports). Prompts go in copyable code blocks.
- **Keep agent output small.** Agents hand back ~20–30 lines and leave full tables, prompts and plan JSON in `{tmp}/reports/<job>/`. Pass those paths on (style agent → editor and QA) instead of the content, and show the user the deliverable table from the file without re-summarising: `plan_table.txt` for plans; for prompts, paste `prompts.txt` in chat (every prompt in full, each in its own code block, lock lines in full).
- **Every dispatch passes paths, not content:** `pack` (`{tmp}/reports/<job>/pack_<style>.md`), `inventory` (`{tmp}/reports/<job>/inv/inventory.json`, when client B-roll exists), `timings` (the `media_timing.py vo` JSON file) and `timings_compact` (the `--compact` text), and `limits` (`{tmp}/reports/<job>/limits.json`). Templates in `reference/steps.md`.
- **Re-runs post only what changed:** only the changed sentences of a fixed prompt (or the prompt file path), not the whole prompt and its locks. After a small fix run `qa` with `scope: delta` and `changed:`; a full QA run is for the first pass at each gate, or when QA says the change reaches further.
- **Job card:** keep a running card (client, product, style, video folder, brief checklist, script, VO path + timings, B-roll source, generator, music, project name, timelines). Re-show it when it changes.

## The 12 steps
1. ⛔ **Brief.** Ask for the brief (PDF, docx, Notion URL or pasted), reference videos, and the per-video folder under `{root}/`. If they came with the request, just confirm the folder exists and go on.
2. **Study the brief** (steps.md covers PDF, docx, Notion and video).
   - Build the **brief checklist**: every rule quoted with its source (length, ratio, tone, hook/CTA rules, must-show / never-show, claims, music and SFX, text style, export settings, deadline).
   - Study the reference videos (frames + transcript) and pick the style.
   - If the user or brief wants a reference's graphic look and `motion\CATALOGUE.md` has no match, dispatch `motion-designer` with the reference and a few client-footage frames. Its style spec and templates feed the style agent's plan.
   - ⛔ Show the checklist and style; ask the user to confirm or add.
   - Once it's confirmed, write `{tmp}/reports/<job>/limits.json` (`<job>` = product name, no spaces) with only the keys the brief fixes: `min_s`, `max_s`, `ratio` (e.g. "9:16"), `fps`, `caption_band_px` (400), `no_text`. The plan check and QA read it.
   - **Before step 3, once per job:** write the context pack, `"{python}" "{root}/.claude/edit-mo-to/tools/context_pack.py" <style> [--client <client>] [--generator google-flow|seedance] --out "{tmp}/reports/<job>/pack_<style>.md"` (rewrite it once if the generator is only chosen at step 6; otherwise reuse it unchanged, for the style agent and QA). When the client gave B-roll: the inventory, once, `"{python}" "{root}/.claude/edit-mo-to/tools/sheets.py" inventory "<client_broll_folder>" "{tmp}/reports/<job>/inv" > "{tmp}/reports/<job>/inv/inventory.json"` (create the `inv` folder first); fix rounds reuse it.
3. **Script.**
   - Brief has a script: use it word for word.
   - No script: ⛔ ask your questions, write it, run `qa` (gate `script`), ⛔ wait for approval.
   - ⛔ **"Storyboard first?"** Ask once the script is set (yes for new clients, new styles or AI-heavy ads; skip for repeat formats). If yes: ask the B-roll source and generator now (step 6's questions, not asked again later). **Images first, board second:**
     1. Dispatch the style agent (`mode: storyboard`, phase `prompts`). **Paste every image prompt in chat, each in its own code block, never only in a file.** Character first: any character-driven ad (always Pixar / claymation) starts with the **character sheet prompt** (one per recurring character). ⛔ Wait: "Generate the character sheet and send it to me / tell me when it's saved."
     2. Then the **storyboard keyframe prompts** (`SB-1…`), written to match the approved character sheet(s) (attach them as references). ⛔ Wait: "Generate the keyframes and tell me when they're saved in <folder>/storyboard/."
     3. Only when the images are saved: dispatch the style agent again (phase `board`) to build the whole storyboard from the real images (`storyboard.py`), show the `storyboard.html`, and ⛔ ask "Approve this direction, or tell me what to change?" Never build the board before the images exist.
     The approved storyboard is the plan for step 6: its shots and graphics carry over, and the keyframes become the AI clips' start frames.
   - TikTok product ad: no script. **Music first:** ⛔ "Suno prompt or your own no-copyright YouTube music?", wait for the track, go to step 5 (beats).
4. ⛔ **Voiceover.** Wait for the user's ElevenLabs file. Note whether it's **one file** (hooks + body) or **one per hook/body**; it sets each timeline's `vo_in`/`vo_out`.
   - **Reusing an existing VO** (saves credits): `media_timing.py vo <file>` with no script, show its sentences with times, ⛔ let the user pick the spans. The script becomes those spoken lines; each timeline's `vo_in`/`vo_out` is its span.
5. **Timing.** VO: `media_timing.py vo <vo> <script.txt>` (script lines in a temp txt); show the line timings. Any `matched: false` line is a ⛔ check (mispronounced or changed words). Music (product ads): `media_timing.py beats <music>`.
   - Save both forms once: the JSON to `{tmp}/reports/<job>/timings.json` (`timings`, for the tools) and `media_timing.py vo <vo> <script.txt> --compact` to `{tmp}/reports/<job>/timings.txt` (`timings_compact`, for agents to read; it reuses the cached transcript). Keep the script txt as `script_file`.
   - **Talking-head A-roll with its own audio** (avatar, creator, host recording): clean it first. `speech_cuts.py propose <clip> --out {tmp}/cuts/<name>.cuts.json` (reuses the cached transcript) finds dead air (pauses over 0.55s trimmed to a breath; edges snapped to real silence) and stutters / false starts / retakes. Silence cuts apply automatically. ⛔ Show the mistakes as a table (`id | type | cut | removes | keeps | recommend`) and ask which to cut; emphasis ("never, never") looks like a stutter. Then `speech_cuts.py apply <cuts.json> --approve <ids> --reject <ids> --script <script.txt>`. Its `keep.json` (`segs`, re-timed `words` and `lines`) replaces the VO timings for that clip and goes to the style agent as `aroll_cuts`. Tighter pacing: `--gap 0.3 --breath 0.15`.
6. **B-roll and prompts.**
   - ⛔ "Use the client's B-roll, generate AI video, or both?" If AI: ⛔ "Where will you generate: Seedance or Google Flow?"
   - Dispatch the style agent (`mode: prompts`): one per timeline or ad, all in one message, each with its own `job` (e.g. `<Product>_T02`) so their files don't overwrite each other. Each runs `plan_tools.py prompts` + `check-prompts` until clean. Then `qa` (gate `prompts`), one per timeline in one message: it runs `qa_check.py prompts` first and judges only meaning and brief rows.
   - Show the table and prompts (paste `prompts.txt`). Fix QA FAILs by re-dispatching (then delta `qa` on the fixed rows), or list unresolved ones for the user.
7. ⛔ **Gather and build.**
   - If AI clips are needed, wait until the user says where they are, then QC the batch with `qc_clips.py run <clips folder> <expected.json>` (write `expected.json` from the prompts table: name, length, keywords, product/phone, use span). It checks length, size, baked-in text, product and phone visibility, and prints PASS/FLAG per clip; open the contact sheets of FLAG clips only, and ⛔ ask the user to regenerate real failures.
   - Dispatch the style agent (`mode: edit-plan`): one per ad (project), all in one message; never one per timeline, because a project's `plan2.json` shares blocks (the body) across its timelines and the build and `qa_check` take that one plan. Plan `overlays` use `motion\CATALOGUE.md` templates and the **editor renders them** during the build; only a graphic no template covers needs `motion-designer` first. Keep the plan's `music` null (except product ads): music goes in at step 11, and `qa_check` FAILs a planned music track the build doesn't have.
   - Then, in this order:
     1. `"{python}" "{root}/.claude/edit-mo-to/tools/plan_tools.py" check "{tmp}/reports/<job>/plan.json" --limits "{tmp}/reports/<job>/limits.json"`. Don't go on while it prints errors: send them back to the style agent.
     2. Dispatch `editor` (`action: build`, project name = product name, hooks as timelines, the plan path, `import_files` = every file the user gave for this video). It builds the whole project in one `build_project.py build` call, imports the files into the media panel, builds from the originals and writes the clip sheets. If the project name is taken, ⛔ ask for another (e.g. "<Product> 2").
     3. `"{python}" "{root}/.claude/edit-mo-to/tools/qa_check.py" build "{tmp}/reports/<job>/plan.json" "{capcut_drafts}/<Product>" --limits "{tmp}/reports/<job>/limits.json" --search "<client folder>" > "{tmp}/reports/<job>/qa_check.json"` (the mechanical checks, no eyes).
     4. Run `qa` (gate `build`, one per timeline in one message) with `qa_check` = that file: it judges only the sheets and the brief rows.
     5. Fixes: the style agent edits `plan2.json` rows and re-expands, `check` again, the editor applies them as `revise-in-place` (patch ops), then `qa_check.py build … --changed <#s>` and a delta `qa`.
   - Show the editor's report and QA verdict. Send the user to CapCut only once QA passes, or with the remaining issues listed.
8. **Transitions and effects** are in the edit plan where they fit the style and brief: few and subtle (3–5 of ≤0.3 s at section changes), each with a whoosh. To add them to a built timeline, the editor uses `capcut_project.py patch` op `transition` (copies a cached CapCut effect from a past project).
9. ⛔ **Review loop.** The user reviews in CapCut and edits it themselves or gives changes. For each change, ⛔ ask which timeline, and new timeline or in place (in place makes a backup), and ⛔ ask them to quit CapCut completely (it rewrites projects on close and would drop our change; the tool refuses while CapCut.exe runs).
   - Ask "quit CapCut" once per review round, before that round's first write, not before every write.
   - The hand-edit diff runs before any write (`edit_diff.py diff --last`, by the editor), so the user's edits are reported and logged, never lost.
   - Then: style agent (`edit-plan` + `revision`), `plan_tools.py check`, `editor` (`revise-new-timeline` | `revise-in-place`; in place passes `old_plan` and `new_plan`, and small timing, swap and scale changes become `patch` ops, not a rebuild), `qa_check.py build` + `qa` (`build`, delta with `--changed` for small changes).
   - **Overlay tweaks** ("move the card up") stay in the main conversation: change the vars, re-render with `motion_render.py`, preview, then have the editor swap the files. No agent for small tweaks.
   - Repeat until the user is happy.
10. ⛔ **Captions.** Remind the user to run CapCut auto-caption; wait until done.
11. ⛔ **Music** (non-product-ad styles): "Suno prompt from me, or no-copyright YouTube music?"
    - Suno: write the prompt; max 18s, so split into parts with crossfade notes.
    - When the file arrives: ⛔ ask which timeline(s) and to quit CapCut, then `editor` `action: add-music`. It **merges** the music (about −20 dB under the VO), keeping captions and hand edits, with a backup.
    - The editor builds a music-only draft (`build_project.py music`) and merges it with `add-tracks`. Only now does the project get music; until step 11 the plan's `music` stays null.
12. **Export** is the user's. Then run the **learning step** (`reference/learning.md`).

## Tools
- Python: `"{python}"`; tools in `{root}/.claude/edit-mo-to/tools/`:
  - `media_timing.py`: `vo <audio> [script.txt] [--compact]`, `beats <audio>`
  - `context_pack.py <style> [--client c] [--generator g] --out pack.md`: the rules one dispatch needs (step 2, once per job)
  - `sheets.py`: `inventory <folder> <out_dir>` (client B-roll catalogue, once per job), `clips <plan> "<timeline>" <out_dir> [--ai]`, `overlays <plan> "<timeline>" <out_dir>` (frame sheets for QA)
  - `plan_tools.py`: `expand`, `check` (step 7, before the build), `prompts`, `check-prompts`, `ops` (style agents and the editor run them)
  - `build_project.py`: `build`, `timeline`, `music` (the editor's one-shot build)
  - `qa_check.py`: `build <plan> "<project>" [--changed …] [--limits …]`, `prompts <prompts2.json>` (mechanical QA, no eyes)
  - `learn.py`: `propose`, `decline`, `save` (learning step)
  - `speech_cuts.py`: `propose <clip>`, `apply <cuts.json>` (dead air and mistake cuts, step 5)
  - `qc_clips.py`: `run <clips folder> <expected.json>` (batch QC of generated clips, step 7)
  - `plan_build.py` / `plan_preview.py`: frame-based plans (the editor's quick route), plan checks, preview mp4
  - `rehearse.py prepare <clip>`: the `/practice-muna` practice job
  - `storyboard.py <storyboard.json>`: the storyboard sheet (step 3), one shareable HTML page
  - `edit_diff.py`: `diff --last <project> <timeline>` (hand edits since our last write: before every revision and at the learning step), `snapshot`, `diff`, `history`
  - `capcut_project.py`: `list <project>` (show timelines); the editor uses the rest.
  - `motion_render.py`: `list`, `render <template> <out.mov> --vars-file f.json`, `preview <mov> <png>`. Catalogue: `motion/CATALOGUE.md`.
  - `plan_preview.py <plan.json> <out.mp4>`: ffmpeg preview of a frame-based plan with overlays.
  - `playbook_scan.py <slug> <folderToken> <outdir>`: contact sheets of a shared Playbook folder without downloading. Its organization header is exchange-life; change it for other clients.
- ffmpeg and ffprobe are on PATH. Temp files go in `{tmp}/` (short path).
- Agents reuse their prompt cache across re-runs within an hour when Claude Code runs with `CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL=1h` (an environment setting, not a file here); suggest it if fix rounds are slow.
