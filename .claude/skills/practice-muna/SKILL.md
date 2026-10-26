---
name: practice-muna
description: Practice run of the full edit-mo-to workflow on the editor's own raw clip, shrunk to a 10-second video. Same 12 steps, same stops, same agents as a real client job, with a short "in a real job" tip at each stop, so a new user learns the workflow (and checks their install) before working on a real client. Use when the user runs /practice-muna, or asks to practise, rehearse, test-drive or demo the workflow.
---

# /practice-muna

A practice run ("practice muna": practise first) is a **real `/edit-mo-to` job, only 10 seconds long.** Run the 12 steps of `{root}/.claude/skills/edit-mo-to/SKILL.md` exactly as written: the same order, the same ⛔ stops, the same agents (style agent, `editor`, `qa`, `motion-designer` if needed), the same tools and the same tables. Read that file and `reference/steps.md` first. Only the inputs change (table below), so the user feels the real workflow, just faster.

**At every ⛔ stop:**
- Ask the real question, offer the suggested answer from the table (the user can just accept it), and keep it to one short message.
- Add **one line** starting "In a real job:" that says what would happen with a client (e.g. "In a real job: you'd generate this voiceover in ElevenLabs and send me the file.").
- Talk in plain, beginner-friendly words.

**Speed:** everything is about 10 s, so keep agent jobs small, run independent agents in parallel, and skip nothing. A rehearsal takes about 15–25 minutes.

## Before step 1
⛔ "Send me a raw video to practise on: any clip of you (or anyone) talking to the camera, at least 15 seconds, straight from your phone." When it arrives, run `PYTHONIOENCODING=utf-8 "{python}" "{root}/.claude/edit-mo-to/tools/rehearse.py" prepare "<raw video>"` (about 1 minute the first time). It lays out a practice job in `{root}/_practice/<name>/`: `brief.md`, `script.txt`, `keep.json`, `broll/`, `music.wav` and `prepare.json` (palette, the speaker's face box, word frames, beats). Say: "I made a practice job from your clip. Now we do exactly what we'd do for a client."

## The 12 steps, rehearsal inputs
| Step | Real job | Rehearsal input · suggested answer |
|---|---|---|
| 1 Brief | the client's brief, references, video folder | `brief.md` + folder `{root}/_practice/<name>/`. Show the brief; no reference video. |
| 2 Checklist + style | every brief rule, style picked | build the checklist from `brief.md` (8 rules); style **UGC talking head** (`ugc`). Suggested: "Looks right." |
| 3 Script + storyboard | the brief's script or one you write; "Storyboard first?" | the script is `script.txt` (what was said, word for word). Suggested storyboard answer: **yes**, 4–5 panels (`mode: storyboard`, real frames from the clip; graphics in the brief's colours). |
| 4 Voiceover | the editor's ElevenLabs file | the clip's own audio is the voiceover. Suggested: "Use the clip's audio." |
| 5 Timing + clean-up | `media_timing.py vo` and `speech_cuts.py` with the stutter stop | already run by `prepare`: show its line timings (`keep.json` `lines`), the dead air removed and any stutters, and ask the stutter question if there are any. `keep.json` is the `aroll_cuts`. |
| 6 B-roll + prompts | "Client B-roll, AI, or both?", generator, prompts table, `qa` prompts gate | suggested: **client B-roll** (`broll/` = moments from the same clip). Run the style agent in `mode: prompts` and `qa` (gate `prompts`) as usual. Also write **one** sample AI prompt marked OPTIONAL, so they see what one looks like; nothing needs generating. |
| 7 Build + QA | style agent `edit-plan`, `editor` build, `qa` build gate | the same, with this showcase brief for the style agent: in about 10 s, on the spoken words, use kinetic type for the hook, `big-text` with `"cutout": true` (text behind the speaker) on the key noun, punch-ins at phrase breaks, one proof card (`checklist`, `glass-counter`, `notify` or `glass-card-v2`), `phone-cards` with B-roll from `broll/`, and an ending `title-card` or `morph-flow` with a call to action, all with `"sfx": "default"`, at most 2 graphics at once, never over `speaker.face`. Project name **Practice – <name>**. Build it the same way as a real job: `plan_tools.py check`, then the `editor` (`action: build`, one `build_project.py build` call: overlays, cutout, SFX, import and the learning snapshot), then `qa_check.py build` and `qa` on the sheets. Show the user the clip and overlay sheets from the editor's report in chat, so they see the result before opening CapCut. |
| 8–9 Review loop | the editor reviews; changes as new timeline or in place | suggest one small change to practise the loop (e.g. "make the hook text bigger" or "swap one B-roll"); do it on a **new timeline**, as in a real job, including the "quit CapCut" stop. |
| 10 Captions | the editor chooses: they run CapCut auto-caption, or Claude adds simple text captions (`editor` `add-captions`, then `qa_check.py captions`) | ask the real step-10 question. Suggested: **"you add them"**, so the caption tool is tested on this computer (the script's exact words, a pop-in, no word-by-word animation; for an animated look, CapCut's caption presets). Tip: on a real job either answer is fine; a script that is not English or Filipino also carries the `TEMP_EN_delete_me` track from the first build, deleted before export. |
| 11 Music | Suno prompt or no-copyright YouTube music | suggested: use `music.wav` (a practice bed made on this computer). Add it the real way (`editor` `add-music`: merged, keeps the captions). Also show a sample Suno prompt they could use next time. |
| 12 Export + learning | the editor exports; the learning step | the same: they export, then run the learning step (`reference/learning.md`) on their hand edits. In a rehearsal, propose rules but save nothing unless they ask. |

## After step 12
A short wrap-up: what each step was for (one line each), what worked on this computer (transcription, dead-air cutter, templates, cutout, frame sheets, CapCut build, captions, music merge, learning diff), and the one fix for anything that failed (the README's "Manual setup"). End with: "You're ready for a real client: type /edit-mo-to and send the brief."

Never add captions before step 10, except the `TEMP_EN_delete_me` review track; at step 10 the editor chooses. Never upload or send the video anywhere.
