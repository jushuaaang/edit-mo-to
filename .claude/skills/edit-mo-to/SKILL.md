---
name: edit-mo-to
description: The user's end-to-end client video workflow - from client brief to a finished CapCut project. Use when the user runs /edit-mo-to, starts a new client video or ad (UGC, B-roll, claymation, Pixar-style, product/TikTok ad), shares a client brief or trial instructions (PDF, docx, Notion link, pasted text), or wants a video edited/assembled in CapCut. Runs 12 gated steps, dispatches the style, editor and QA agents, and learns the user's preferences at the end.
---

# edit-mo-to

This is the user's own editing workflow. You run it in the main conversation, and you own all talk with the user. Agents do the heavy, self-contained work: `ugc`, `broll`, `claymation`, `pixar` and `product-ad` (style), `motion-designer` (new looks and templates only), `editor` (builds CapCut and renders overlays), and `qa` (checks).

**Before step 1, read** `D:\Video Editing\.claude\edit-mo-to\preferences.md` (General) and, once you know the client, `D:\Video Editing\.claude\edit-mo-to\clients\<client>.md`. Read `reference/steps.md` for the exact gate wording and the agent dispatch templates.

## Hard rules
- **STOP at every gate** marked ⛔. Ask, and wait for the user's answer. Never assume a choice the process says to ask about. ("we will do this step by step, you will not proceed until I say proceed")
- **The brief is law.** Every rule from it goes on the brief checklist, and QA checks it.
- **Deliverables go in chat, as tables.** Never write them to .md files. Prompts go in copyable code blocks.
- **Formats:** times in `seconds:frames` at 30 fps; full file paths; 9:16 unless the brief says otherwise.
- **Captions** are done by the user (CapCut auto-caption), so never add them. **Export** is done by the user.
- **Track state** in a running "Job card" (client, product, style, video folder, brief checklist, script, VO path + timings, B-roll source, generator, music, project name, timelines). Re-show it when it changes.

## The 12 steps
1. ⛔ **Brief.** Ask for the client's brief or instructions (PDF, docx, Notion URL, or pasted text) and any reference videos. Also ask for the per-video folder path the user made under `D:\Video Editing\`.
   - If the brief, references and folder already came with the request, don't ask again: confirm the folder exists and go to step 2.
2. **Study the brief.**
   - Read everything (see steps.md for PDF, docx, Notion and video handling).
   - Build the **brief checklist**: every rule quoted with its source, covering length, ratio, tone, hook/CTA rules, must-show and never-show items, claims, music and SFX, text style, export settings, and deadline.
   - Study the reference videos: frames and a transcript.
   - Pick the style from the brief.
   - **If the user or brief wants a reference's graphic look** ("make it like this") and `motion\CATALOGUE.md` has no matching style, dispatch the `motion-designer` with the reference video and a few frames of the client footage. It returns a style spec plus new templates, which the style agent then uses in the edit plan.
   - ⛔ Show the checklist and the style, and ask the user to confirm or add anything.
3. **Script.**
   - **Brief has a script:** use it word for word.
   - **No script in the brief:** ⛔ ask your questions, write a script, and run `qa` (gate `script`). ⛔ Wait for the user's approval.
   - **TikTok product ad:** no script. Jump to **music first**: ⛔ ask "Suno prompt or your own no-copyright YouTube music?" and wait for the track, then go to step 5 (beats).
4. ⛔ **Voiceover.** If a VO is needed, wait for the user's ElevenLabs file (path or attachment). Note whether it's **one file** holding hooks and body, or **one file per hook/body**; it changes how each timeline takes its VO (`vo_in`/`vo_out`).
   - **Reusing an existing VO** (e.g. to save ElevenLabs credits): transcribe it (`media_timing.py vo <file>` with no script), show its sentences with times, and ⛔ let the user pick the spans. The script becomes those exact spoken lines, and each timeline's `vo_in`/`vo_out` is its span in that file.
5. **Timing.**
   - **VO:** run `media_timing.py vo <vo> <script.txt>` (write the script lines to a temp txt) and show the line timings table. Any line with `matched: false` is a ⛔ check with the user (mispronounced or changed words).
   - **Music (product ads):** run `media_timing.py beats <music>`.
6. **B-roll and prompts.**
   - ⛔ Ask: "Use the client's B-roll, generate AI video, or both?" If AI is involved, ⛔ ask: "Where will you generate: Seedance or Google Flow?"
   - Dispatch the style agent (`mode: prompts`), then run `qa` (gate `prompts`).
   - Show the table and prompts. Fix QA FAILs by re-dispatching first, or list any unresolved ones for the user.
7. ⛔ **Gather and build.**
   - If AI clips are needed, wait until the user says they're generated and where they are, then inventory them (ffprobe).
   - Dispatch the style agent (`mode: edit-plan`).
   - **Overlays:** the plan's `overlays` use templates from `motion\CATALOGUE.md`, and the **editor renders them during the build**, with no extra agent. Only if the plan needs a graphic no template covers, dispatch the `motion-designer` first to create it.
   - Then the `editor` (`action: build`, project name = product name, hooks as timelines, the plan, plus `import_files` = every file the user gave for this video).
   - The editor imports those files into the CapCut project's media panel and builds the timeline from the imported originals, not copies.
   - Run `qa` (gate `build`).
   - If the editor reports the project name is taken, ⛔ ask the user for another name (e.g. "<Product> 2").
   - Show the editor's report plus the QA verdict. Only send the user to CapCut once QA passes, or with the remaining issues listed.
8. **Transitions and effects** are part of the edit plan where they fit the style and brief.
9. ⛔ **Review loop.** The user reviews in CapCut, then either edits it themselves or gives changes. For each change request, ⛔ ask:
   - **Which timeline?**
   - **New timeline or work directly in it?** (In place makes a backup first.)
   - ⛔ "Please quit CapCut completely before I write to the project." (CapCut rewrites projects when it closes and would drop our change; the tool refuses while CapCut.exe is running.)
   - Then: style agent (`edit-plan` with `revision`), `editor` (`revise-new-timeline` or `revise-in-place`), and `qa` (`build`).
   - **Overlay tweaks** ("move the card up", "make the title bigger") are handled here in the main conversation: change the vars, re-render with `motion_render.py`, preview, then have the editor swap the files. Don't dispatch an agent for small tweaks.
   - Repeat until the user is happy.
10. ⛔ **Captions.** Remind the user to run CapCut auto-caption, and wait until they say it's done.
11. ⛔ **Music** (non-product-ad styles). Ask: "Suno prompt from me, or will you find no-copyright YouTube music?"
    - **Suno:** write the prompt. Suno max is 18s, so split it into parts with crossfade notes.
    - **When the file arrives:** ⛔ ask which timeline(s) to add it to, and to quit CapCut completely. Then dispatch the `editor` with `action: add-music`. It **merges** the music into those timelines, keeping the user's captions and hand edits (with a backup), at about −20 dB under the VO.
12. **Export** is done by the user. Then run the **learning step** (`reference/learning.md`).

## Tools
- Python: `"D:\Video Editing\.claude\edit-mo-to\tools\.venv\Scripts\python.exe"`
- `...\tools\media_timing.py`: `vo <audio> [script.txt]`, `beats <audio>`
- `...\tools\capcut_project.py`: `list <project>` (for showing timelines). The editor uses the rest.
- `...\tools\motion_render.py`: `list`, `render <template> <out.mov> --vars-file f.json`, `preview <mov> <png>`. Templates: `...\motion\CATALOGUE.md`.
- `...\tools\plan_preview.py <plan.json> <out.mp4>`: ffmpeg preview of a frame-based plan with its overlays.
- `...\tools\playbook_scan.py <slug> <folderToken> <outdir>`: scans a shared Playbook folder into contact sheets without downloading anything. The organization header is set to exchange-life; change it for other clients.
- ffmpeg and ffprobe are on PATH. Write temp files to `C:\Users\Keytech\mcp-servers\tmp\` (short path).
