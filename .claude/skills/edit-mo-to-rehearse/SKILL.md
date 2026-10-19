---
name: edit-mo-to:rehearse
description: Test-drive edit-mo-to on a new computer, or show off what it can do. The editor gives one raw video of someone talking; Claude cuts it to a 10-second showcase edit with the full motion-graphics range (kinetic type, text behind the speaker, punch-ins, cards, phone cards, sound design, music), previews it, then builds it in CapCut. Use when the user runs /edit-mo-to:rehearse, asks to rehearse, test-drive or demo the workflow, or wants to check a fresh install.
---

# /edit-mo-to:rehearse

A 10-second showcase of everything edit-mo-to can do, made from the editor's own raw video. It doubles as the install check: transcription, the dead-air cutter, the motion templates, the speaker cutout, the preview and the CapCut build all run once.

**Paths:** `{root}`, `{python}`, `{tmp}`, `{capcut_drafts}` from `.claude/edit-mo-to/machine.json` (see CLAUDE.md). Tools are in `{root}/.claude/edit-mo-to/tools/`; run them with `PYTHONIOENCODING=utf-8 "{python}"`. Talk in plain, beginner-friendly words; stop at every ⛔.

## Steps
1. ⛔ **Ask for the raw video:** "Send me a raw video to edit: any clip of you (or anyone) talking to the camera, straight from your phone, at least 15 seconds. Optional: your brand colours or logo, and the call to action you want at the end." Use their colours if given; otherwise the palette comes from the video.
2. **Prepare:** `rehearse.py prepare "<raw video>"` (about 1 minute). It transcribes, cuts dead air and stutters, picks the best ~10 s (whole sentences), finds the speaker's face box, takes a palette from the footage and makes a license-free music bed with beats. Everything lands in `{root}/_rehearse/<name>/prepare.json`.
   - ⛔ Show what it chose: the 10 s of text, the dead air removed and any stutters cut. Ask: "Edit this part, or pick another?" (`--start <seconds>` for another part).
3. **Design the showcase plan:** write `{root}/_rehearse/<name>/plan.json` in the frame-based plan format (`plan_build.py` docstring; example `tools/examples/cirelle_apple_ui_plan.json`). Use `plan_segs`, `clips_dir`, `words`, `palette`, `speaker`, `other_moments` and `music` from prepare.json; set `motion_dir` to `{root}/_rehearse/<name>/motion/`. The goal is the full range in 10 s, and it must still look like a premium edit, not a demo reel:
   - **0–1.5 s, hook:** `kinetic-type` on the first key words (on their word frames), a `light-sweep` or `color-flash` on frame 0, and a punch-in.
   - **Text behind the speaker:** `big-text` with `"cutout": true` on the strongest noun or number, inside one seg, for 1–2 s.
   - **Punch-ins:** split `plan_segs` at sentence or phrase breaks and alternate scale 1.0 / 1.12–1.2 on emphasis words; never two punch-ins in a row.
   - **Proof beat:** one of `data-viz` / `glass-counter` (when a number is spoken), `checklist`, `notify` or `glass-card-v2`, matched to what is said.
   - **The editor's own clips:** `phone-cards` (`float`) using the raw video at `other_moments` (`video1–3` = the raw file, `start1–3` = those times) for about 1.5 s.
   - **Ending:** `title-card` or `morph-flow` with their CTA (or "Comment EDIT" when none was given) over the last 1.5–2 s.
   - **Sound:** `"sfx": "default"` on every overlay; `"music": {"file": <music.wav>, "volume": 0.08}` under the voice.
   - **Rules:** at most 2 graphics on screen at once; every graphic starts on a spoken word or a cut; nothing covers `speaker.face` (except the cutout beat, where the text is behind the head); two fonts at most, chosen for the mood of what is said; colours from the palette or their brand. Then `plan_build.py plan.json --snap-beats <beats.json> --tracks ui,flash` for the overlays not locked to a word (`"snap": false` on word-locked ones); write the beats list from prepare.json to `beats.json` first.
   - **Tracks:** overlays on one track must never overlap in time; give extra layers their own track (e.g. `"tracks": {"ui": 5, "ui2": 4, "title": 6, "flash": 7, "cutout": 8}`). `plan_build.py` checks this before rendering.
4. **Render and self-check:** `plan_build.py plan.json --render-only` (overlays and cutouts; about 3 minutes on CPU the first time; later runs render only missing files, so after a fix delete just that `.mov`, or use `--force` to redo all), then `plan_preview.py plan.json "{root}/_rehearse/<name>/preview.mp4" 0.5,2,4,6,8`. Read the five frames. Fix anything that covers the face, reads badly, clips, or looks like AI slop, then re-render only what changed.
5. ⛔ **Show the preview:** send `preview.mp4` to the user, with a short table `Time | What you see | Capability` (one row per effect). Ask: "Build this in CapCut, or change something first?"
6. **Build in CapCut:** ⛔ ask them to quit CapCut completely. Then `plan_build.py plan.json` (prints the draft), `capcut_project.py wait "<draft>"`, and `capcut_project.py compose "{capcut_drafts}/Rehearse – <name>" "Timeline 01 – Rehearse=<draft>"`, then `capcut_project.py import "{capcut_drafts}/Rehearse – <name>" "<raw video>" "<music.wav>"`. Snapshot it for the learning demo: `edit_diff.py snapshot "{capcut_drafts}/Rehearse – <name>" "Timeline 01 – Rehearse" "{root}/_rehearse/<name>/built.json"`. If the name is taken, add a number.
7. **Hand-off:** "Open CapCut: the project is **Rehearse – <name>**. Change anything you like (trim a clip, move a graphic, change the music volume), then tell me 'done' and I'll show you what I would learn from your edits." On "done": `edit_diff.py diff "{root}/_rehearse/<name>/built.json" "{capcut_drafts}/Rehearse – <name>" "Timeline 01 – Rehearse"` and explain the patterns in plain words. In a rehearsal, save nothing to the preferences unless the user asks.
8. **Install report:** a short checklist of what worked on this computer: transcription, dead-air cutter, motion templates, cutout, preview, CapCut build, learning diff. For anything that failed, give the one fix to try (the README's "Manual setup" has the details).

Never add captions (in a real job the editor adds them in CapCut). Never upload or send the video anywhere.
