# edit-mo-to: step detail

## Reading briefs (step 2)
- **PDF:** use the Read tool (pages param for long files). **.docx:** `python -c "import zipfile,re;x=zipfile.ZipFile(r'<f>').read('word/document.xml').decode();print(re.sub(r'<w:p[^>]*>','\n',re.sub(r'<(?!w:p)[^>]+>','',x)))"`, or ask the user to paste it if that fails.
- **Notion:** public pages via WebFetch, one call per page, and follow links to sub-pages the brief points to (checklists, examples). If a page needs login or returns nothing, ⛔ ask the user to paste or export it. The Notion connector isn't authorised.
- **Reference videos:**
  - `ffprobe` for duration, fps and size;
  - a contact sheet (`ffmpeg -i "<v>" -vf "fps=1,scale=240:-1,tile=6x5" -frames:v 1 "{tmp}/ref_sheet.jpg"`), which you then Read;
  - extract audio and transcribe with `media_timing.py vo`.
  - Note: cut rhythm (cuts/sec), layouts, text style, hook pattern, music energy.
- **Checklist format** (a table in chat): `# | Rule (quoted) | Source | Applies to (script/prompts/edit/export)`.
- **Questions about the brief** (shown under the checklist at the same gate): unclear, implied, conflicting or missing rules, at most 6, numbered, most important first, each ending with what it changes (e.g. "changes the hook length"). Conflicts with `preferences.md`/`my-preferences.md` are asked too; until answered, the brief wins. Answers go in the checklist as rows with Source `editor, <date>`; a skipped question gets the default you'll use as a row with Source `assumed, <date>`. None: write "No questions about the brief."

## Choosing the style
- UGC host / selfie review → `ugc`
- VO + client footage / stock → `broll`
- Clay / stop-motion → `claymation`
- 3D animated story → `pixar`
- Music-only product or TikTok → `product-ad`

If the style is mixed (e.g. UGC host + heavy B-roll), pick the main one and pass the secondary rules in the dispatch. If unsure, ⛔ ask.

## Dispatch template (style agents)
```
mode: storyboard (phase: prompts | board) | prompts | edit-plan
client: <client file stem or "new">   product: <Product>   job: <Product, no spaces>
pack: {tmp}/reports/<job>/pack_<style>.md
video_folder: <path>
brief_checklist: <the table>
script: <numbered lines with Hook/Body/CTA labels>   script_file: <the same lines in a txt, one per line>
timings_compact: {tmp}/reports/<job>/timings.txt   (media_timing vo --compact; or beats for product ads)
timings: {tmp}/reports/<job>/timings.json          (the JSON, for the tools' --timings)
limits: {tmp}/reports/<job>/limits.json
broll_source: client | ai | both     generator: higgsfield | google-flow     generator_model: <model id from generators.json, or the name the editor gave> (either site)
vo: <path(s): one file, or one per hook/body>   music: <path or none>   (product ads: music is required; others: none until step 11)
client_broll_folder: <path or none>   (check that it exists before dispatching)
inventory: {tmp}/reports/<job>/inv/inventory.json, or one inv_<subfolder>/inventory.json per shortlisted subfolder of a big library   (when client B-roll exists)
revision: <requests + target timeline>      (review loop only)
aroll_cuts: <keep.json path(s) from speech_cuts.py>   (talking-head A-roll only)
script_lang: <es | de | en | fil | …> (media_timing / speech_cuts --lang: the code, but en for English and Filipino)   script_en: {tmp}/reports/<job>/script_en.txt (one per VO file)   (TEMP_EN on: edit-plan writes plan2 `temp_en`)
temp_en_removed: true | [<timelines>]   (only after the editor deleted TEMP_EN_delete_me: everywhere → plan-wide "temp_en_removed": true; from some timelines → "temp_en_removed": true on those plan2 timelines)
```

## Dispatch template (editor)
```
action: build | revise-new-timeline | revise-in-place | add-captions | add-music
job: <Product, no spaces>   project: <Product>
plan: {tmp}/reports/<job>/plan.json   (build, revise-new-timeline, add-captions (a revise-new-timeline timeline: its built plan copy); add-music: the built plan copy <base>/.edit-mo-to/built/<timeline>.plan.json)
script_file: <one VO file's script lines>   timings: <that VO's media_timing vo JSON>   timelines: [<the timelines that play that VO>]   (add-captions only; one dispatch per VO file, e.g. body timelines in one, each hook with its own VO in its own)
temp_en_removed: true   (when the job card says "TEMP_EN removed")
import_files: <every clip, VO, music, B-roll file the user gave for this video>   (build)
timeline: <name>   new_timeline_name: <name>   (revisions)
old_plan: <base>/.edit-mo-to/built/<timeline>.plan.json   new_plan: {tmp}/reports/<job>/plan.json (re-expanded)   (revise-in-place)
segments: <capcut_project segments dump of the timeline>   (revise-in-place, optional: the editor makes it)
music: <path>   music_volume: 0.1   timelines: [<names>]   (add-music only)
client: <client>   video: <video name>   (for the hand-edit log)
```

## Dispatch template (qa)
```
gate: script | prompts | build | captions
style: <style>   client: <client>   job: <Product, no spaces>
pack / brief_checklist / script / script_file / timings_compact / timings / limits: <as above>
prompts: <prompts2.json + prompts.txt paths>          (prompts gate)
plan: <plan.json path; a revise-new-timeline timeline: its built plan copy <base>/.edit-mo-to/built/<new name>.plan.json>   project: {capcut_drafts}/<Product>   timelines: <names>   client_folder: <path>   (build and captions gates)
script_file: <that timeline's VO script lines>   timings: <that VO's media_timing vo JSON>   (captions gate; the same pair the editor's add-captions used)
qa_check: {tmp}/reports/<job>/qa_check.json   (build gate, when the skill ran qa_check.py; captions gate: the editor's qa_captions_<timeline>.json)
script_lang: <code>   script_en: <path>   (TEMP_EN on)
scope: full | delta   changed: <clip #s per timeline, ovN / prompt ids / ops since the last QA>   (delta after a small fix)
```

## Gate wording (keep it short, one question per message; the checklist gate adds its brief questions in the same message)
- Brief: "Send me the client's brief or instructions (PDF, doc, Notion link, or paste it), any reference videos, and the folder you made for this video."
- Checklist: "Here's everything the brief requires. Anything missing or wrong?" Then, when there are any, "Questions about the brief:" and the numbered questions.
- Script approval: "Approve this script, or tell me what to change."
- Storyboard: "Want a storyboard first, so you see my direction before any video is made? (Recommended for new clients and AI-heavy ads.)"
- Character sheet: "Generate the character sheet from this prompt and send it to me (or tell me when it's saved)."
- Keyframes: "Now generate the storyboard images from these prompts and tell me when they're saved in <folder>/storyboard/."
- Storyboard approval: "Here's the full storyboard built from your images. Approve this direction, or tell me what to change."
- VO: "Generate the voiceover in ElevenLabs and send me the file."
- B-roll source: "Use the client's B-roll, generate AI videos, or both?"
- Generator: "Where will you generate: Higgsfield or Google Flow?" Then, for either site: "Which Higgsfield model?" or "Which Google Flow model?"
- Clips ready: "Tell me when all the clips are generated and in <folder>."
- Review: "Which timeline is this change for? And should I make a new timeline for it, or work directly in that timeline (I'll back it up first)?"
- Quit CapCut: "Please quit CapCut completely before I write to the project, and tell me when it's closed."
- Captions: "Captions: will you run CapCut auto-caption yourself, or should I add them? (Mine are simple text captions with the script's exact words and a pop-in; no word-by-word animation. For an animated look, use CapCut's caption presets.)" If they run it: "Run auto-caption in CapCut and tell me when it's done." If I add them: "Which timeline(s)? And please quit CapCut completely before I write to the project, and tell me when it's closed."
- Music: "Do you want a Suno prompt from me, or will you find no-copyright YouTube music?"

## Revision requests
Turn each request into: target timeline, mode (new or in place), new timeline name ("Timeline 0N – <Hook/Body> rev k"), and the exact changes (clip #, what to swap, new times). Pass these to the style agent as `revision`. Small timing or swap changes don't need new prompts unless new AI clips are required. If they are, go back to step 6 for just those clips.

When dispatching `revise-in-place`, don't ask the editor to back up first: `replace` and `patch` already back the timeline up and return the path (an extra request makes two backups). Pass `old_plan` = `<base>/.edit-mo-to/built/<timeline>.plan.json` (what the timeline was last built or patched from; `build_project` writes it, and the editor refreshes it with `mark-built` after each patch) and `new_plan` = the re-expanded `plan.json`. Expand always overwrites `plan.json`, so it can never be the old plan: small timing, swap and scale changes then go in as `patch` ops, keeping the user's edits. A job built before the built plan copy existed has none: the editor seeds it from the plan the timeline was built from (`mark-built`), or falls back to `revise-new-timeline` / `replace` (editor.md).

## GUI (the "Edit Mo To" companion app)
Every command runs from `{root}` as `.claude/edit-mo-to/run gui/job.py <command> "<folder>" …` and prints one JSON line (`{"ok": true, …}`). Run `job.py` calls one at a time, never as parallel Bash calls (each waits for the folder lock, so parallel calls are safe but gain nothing, and their order is then random). Steps: `brief script storyboard voiceover timing prompts clips build review captions music export` (build covers steps 7–8). `job.py --help` lists the commands.

`init` and `step "<folder>" export done` also save the plan's week % (from the project status line) into `job.json` for the dashboard's "A video uses about N% of your week"; nothing to run for it. If export was marked done before any reading existed, `.claude/edit-mo-to/run gui/job.py usage-mark "<folder>" finish` right after your next reply saves the finish (`"usage": null` = still no reading; never guess one). Never mark `start` late: a late start makes the video look cheaper.

### Gates
`gate.json` is `{"title", "detail"?, "questions": [{"id", "text", "why"?, "kind", "options"?, "default"?}]}`; `kind` is `choice | multi | text | confirm | file`. `text` is the gate wording above, word for word. `options` are strings or `{"value", "label"}`. Pass it on stdin (no file outside the project to write, so no permission question):
```
.claude/edit-mo-to/run gui/job.py gate "<folder>" <step> --file - <<'JSON'
{"title": "…", "questions": [{"id": "…", "kind": "confirm", "text": "…"}]}
JSON
```
(`--file <path>` still reads a file; `job.py output … --file -` and `--from <adapter> -` read stdin the same way). The step becomes `waiting`. Then run `.claude/edit-mo-to/run gui/wait.py "<folder>" --after <last seq> --step <step> --timeout 7100` with `run_in_background` and the longest background timeout (`timeout` 7200000 ms, 2 h). `wait.py` prints `{"events": [...]}` and exits 0 when the editor sends something (exit 3 with `{"events": []}`: `--timeout` passed; exit 4: another `wait.py` took over; exit 130 or 143: stopped). When it ends with no events (a timeout, killed, or stopped by Claude Code's background time limit), run it again with the same `--after`, and keep doing so until the gate is answered: an answer can come hours later. A gate answer is an `answer` event with `gate` = the gate id and `target` = the question id; a `stale` answer (to a gate that was replaced) doesn't count. `wait.py` exits on any new event (a message, an edit, an upload, or an answer to just one question), so after each wake handle the events that aren't answers (apply them or note them in chat, mark them handled) and run `wait.py --after <the new highest seq>` again until every question the gate needs is answered, in the GUI or in chat. Only then `close-gate`: closing early turns the editor's later answers into stale "Not counted" ones. Conditional questions are needed only when their condition holds: script `changes` only when `approve` is `false`; `generator_model` once `generator` is answered (both sites ask it); `capcut_closed` only once per review round; on the checklist gate, the brief `questions` answer only when there are brief questions (a skipped one gets its default as an `assumed` row).

One example per kind:
```json
{"title": "approve the storyboard direction", "questions": [
  {"id": "approve", "kind": "confirm", "text": "Here's the full storyboard built from your images. Approve this direction, or tell me what to change."}]}
{"title": "B-roll and generator", "questions": [
  {"id": "broll_source", "kind": "choice", "text": "Use the client's B-roll, generate AI videos, or both?", "options": [{"value": "client", "label": "Client's B-roll"}, {"value": "ai", "label": "Generate AI video"}, {"value": "both", "label": "Both"}]},
  {"id": "generator", "kind": "choice", "text": "Where will you generate: Higgsfield or Google Flow?", "options": [{"value": "higgsfield", "label": "Higgsfield"}, {"value": "google-flow", "label": "Google Flow"}]},
  {"id": "generator_model", "kind": "choice", "text": "Which Higgsfield model?", "options": [{"value": "seedance-2.0", "label": "Seedance 2.0"}, {"value": "seedance-2.5", "label": "Seedance 2.5"}, {"value": "kling-3.0", "label": "Kling 3.0"}, {"value": "veo-3.1", "label": "Veo 3.1"}, {"value": "other", "label": "Other"}]}]}
{"title": "B-roll and generator (Google Flow chosen)", "questions": [
  {"id": "generator_model", "kind": "choice", "text": "Which Google Flow model?", "options": [{"value": "veo-3.1-fast", "label": "Veo 3.1 Fast"}, {"value": "veo-3.1-quality", "label": "Veo 3.1 Quality"}, {"value": "veo-3.1-lite", "label": "Veo 3.1 Lite"}, {"value": "gemini-omni-flash", "label": "Gemini Omni Flash"}, {"value": "other", "label": "Other"}], "default": "<model from generators.py pick --site google-flow, after the colon>"}]}
{"title": "music: timelines", "questions": [
  {"id": "timelines", "kind": "multi", "text": "Which timeline(s)?", "options": ["Timeline 01 – H1 + Body + CTA", "Timeline 02 – Hook 2"], "default": ["Timeline 01 – H1 + Body + CTA"]},
  {"id": "capcut_closed", "kind": "confirm", "text": "Please quit CapCut completely before I write to the project, and tell me when it's closed."}]}
{"title": "script approval", "questions": [
  {"id": "approve", "kind": "confirm", "text": "Approve this script, or tell me what to change."},
  {"id": "changes", "kind": "text", "text": "What should change?"}]}
{"title": "voiceover", "questions": [
  {"id": "vo", "kind": "file", "text": "Generate the voiceover in ElevenLabs and send me the file."}]}
```
**The model Claude picks.** When you choose the model yourself (proposing a default, or generating for the editor), use `generators.py pick` / the editor's default and never a model in their avoid list. `.claude/edit-mo-to/run tools/generators.py pick --site <site>` prints `<site>:<model>` from this computer's Settings ("When Claude picks, never use" = prefs `avoid_models`, "Claude's default model" = `default_model`; none set: the site's first model; exit 1: every model of the site is avoided; exit 3: the settings file can't be read; for both, ask the editor which model and never guess). The `generator_model` question still lists every model of the site (the editor may pick any, avoided or not) and gets `"default"` = the part after `:` of what it prints (the Google Flow example above shows the placeholder; never copy a model id into `default` from a doc or another job: each editor's choice lives only in their own Settings) (the GUI highlights it, and the B-roll & prompts page highlights the same pick before any gate opens).

Working ahead, e.g. the editor picked the music source early: `{"id": "source_ok", "kind": "confirm", "text": "You chose Suno earlier. Still right?", "default": "suno"}` in the music gate, where `source` is asked today. The confirm gets its own id `<id>_ok`, never the choice's id (a gate question with the choice's id hides the page's own buttons for it), and the early value always goes in the text, because the GUI shows a confirm as Yes / No and ignores `default`. Answer `true`: use the early value. Answer `false`: re-open the gate with the original choice question (`{"id": "source", "kind": "choice", "options": [...], "default": "suno"}`; the GUI highlights `default` on a choice), or take the new pick the editor makes on the step page (`answer` `music:source`, still visible while `source_ok` is asked) or in chat.

| Gate (wording above) | Step | Question ids (kind; values) |
|---|---|---|
| Brief | `brief` | `brief` (text). The page's own inputs answer it too: `brief:link`, `brief:paste`, `brief:instructions`, uploads into `refs/` |
| Checklist | `brief` | `checklist` (confirm). The brief questions come back as one `answer` with target `questions` (value `{"<question id>": "<answer>"}`), so don't list them as gate questions |
| Script approval | `script` | `approve` (confirm), `changes` (text) |
| Storyboard first? | `script` | `storyboard_first` (confirm); when yes, then `broll_source`, `generator` and `generator_model` (as step 6) |
| Character sheet | `storyboard` | `character_sheet` (confirm; `true` = every `CHAR-n` is saved as `storyboard/CHAR-n.png`, dropped on its card or saved from outside the app; the gate bar shows it as "It's saved". Check the files are there before going on) |
| Keyframes | `storyboard` | `keyframes` (confirm; the editor drops `SB-n` images on the cards) |
| Storyboard approval | `storyboard` | `approve` (confirm; the page's Approve all answers it with `true`) |
| VO | `voiceover` | `vo` (file) |
| Older-VO spans | `voiceover` | `oldvo` (text; the "Reuse an older VO" dialog answers it with `[{"id", "timeline"}]`) |
| Unmatched lines | `timing` | `unmatched` (choice; `keep` \| `rerecord`) |
| Which cuts | `timing` | `cuts` (multi; the cut ids, recommended ones as `default`) |
| B-roll source / Generator | `prompts` | `broll_source` (choice; `client` \| `ai` \| `both`), `generator` (choice; `higgsfield` \| `google-flow`), `generator_model` (choice; the chosen site's model ids in `.claude/edit-mo-to/generators.json` plus `other`; asked for either site, with the text "Which Higgsfield model?" or "Which Google Flow model?"; `other`: ask the model's name in chat and pass that name as `generator_model`: Higgsfield gives it the table's strictest limits, Google Flow keeps its own 4–8 s, 7-attachment limits; either way with a warning). A Google Flow job with no model keeps today's Flow limits and prompts |
| Clips ready / regenerate | `clips` | `clips_folder` (text), `regenerate` (multi; the FLAG clips) |
| Project name taken | `build` | `project_name` (text, `default` "<Product> 2"; the page's dialog answers it) |
| Review | `review` | `timeline` (choice; the timelines), `mode` (choice; `inplace` \| `new`), `capcut_closed` (confirm) once per round |
| Captions | `captions` | `who` (choice; `me` \| `claude`); then `timelines` (multi) and `capcut_closed` (confirm) |
| Music | `music` | `source` (choice; `suno` \| `own`); then `timelines` (multi) and `capcut_closed` (confirm) |
| Learning step | `export` | `save` (confirm); each proposal also comes back as `learn:<id>` (below) |

Every gate before a CapCut write includes `capcut_closed` (confirm): the page shows the red "Quit CapCut" banner and the "CapCut is still running" dialog for it. On a `capcut_closed` answer of `"cancel"`, drop that change.

**An action or approve event never replaces a gate.** Page buttons that duplicate a gate question answer that question when the step's open gate asks it: Approve all answers `approve`, "Apply selected cuts" answers `cuts`, "Add captions" answers `timelines` (each an `answer` with the gate id, and the gate bar hides the question). Without that question open (no gate, or another gate of the step, e.g. Approve all while the keyframes gate is open) the button sends its `approve` / `action` event: take it only as the default and confirm it at that step's gate, like an early input (`<id>_ok`, e.g. `{"id": "approve_ok", "kind": "confirm", "text": "You approved the whole board earlier. Still approved?"}`); never run the step's work in its place. A CapCut write still needs `capcut_closed`. Answers sent outside a gate while a step runs (`answer` `<step>:<id>` with no gate) count like early inputs too: they are the default, and Claude confirms them at the gate.

### Events the pages send
Read them with `job.py inbox "<folder>" --unhandled`, act on them, then `job.py handled "<folder>" <seq> …`. An early input has `"early": true` and `gate: null` (latest per target wins). `message` events are the "Tell Claude" boxes (a step box has `step`; the right panel has none).

| Step | Event (type, target) | What it asks |
|---|---|---|
| brief | `answer` `brief:link` / `brief:paste` / `brief:instructions`; `upload` `refs:<file>` (+ early `brief:upload`) | the brief, its link, extra instructions, reference files (in `refs/`) |
| brief | `answer` `brief:questions` (no gate) or `questions` (gate) | answers to the brief questions, `{"<id>": "<text>"}`: checklist rows with source `editor, <date>` |
| script | `answer` `script:mode` (`mine` \| `write`), `script:own_script` (early) | use the editor's script / write one |
| script | `edit` `script:<line id>` | the new text of that line (or its English line): update the script and `script_en.txt`, re-store the `script` output |
| storyboard | `edit` `storyboard:<id>:prompt` / `storyboard:<id>:visual` | new keyframe prompt / visual direction for that shot: write it to `storyboard.json` |
| storyboard | `comment` `storyboard:<id>`; `action` `storyboard:<id>` (`"request change"`, `text`) | change that shot: rewrite only it, set its `status` to `changed` |
| storyboard | `comment` `storyboard` | notes on the whole board |
| storyboard | `approve` `storyboard:<id>` | that shot approved: `status` `approved` |
| storyboard | `action` `storyboard:<id>:flagged` (`text`: what the site said, optional) | Got flagged: the image site blocked that shot's keyframe prompt (below, "Got flagged") |
| storyboard | `approve` `storyboard` (Approve all with no `approve` question open) | the editor's go-ahead in advance: the default for the approval gate, confirmed there (`approve_ok`) |
| storyboard | `upload` `keyframe:<SB-n \| CHAR-n>` | an image saved as `storyboard/<id>.png` |
| voiceover | `upload` `vo:<file>` (+ early `voiceover:upload`) | the VO file(s) in `vo/` |
| voiceover | `action` `voiceover:oldvo-transcribe` (value: the file) | transcribe an older VO (`media_timing.py vo` with no script), store it as the `oldvo` output |
| voiceover | `answer` `voiceover:oldvo` (no gate) or `oldvo` (gate), `[{"id", "timeline"}]` | the picked sentences and their timelines |
| timing | `edit` `timing:<line id>` (`keep` \| `rerecord`) | an unmatched line: keep it, or the editor re-records |
| timing | `action` `timing:apply-cuts` (`{"approve": [ids], "reject": [ids]}`; only while no gate asks `cuts`, which the button answers instead) | the picked cuts: the default for the `cuts` gate, confirmed there; then `speech_cuts.py apply` with those ids |
| prompts | `answer` `prompts:broll_source`, `prompts:generator`, `prompts:generator_model` (early) | step 6's answers |
| prompts | `action` `prompts:<prompt id>:flagged` (`text`: what the site said, optional) | Got flagged: the video site blocked that prompt (below, "Got flagged") |
| clips | `answer` `clips:clips_folder` (early); `action` `clips:check` (value: the folder) | run `qc_clips.py run` on that folder |
| clips | `edit` `clips:<file>` (`regenerate` \| `use`) | from the contact sheet: regenerate that clip, or use it anyway |
| storyboard, clips, voiceover | `action` `generate:storyboard:<SB-n \| CHAR-n>`, `action` `generate:clips:<prompt id>`, `action` `generate:voiceover:all` | Generate for me (only on a computer where `.claude/edit-mo-to/run gui/job.py can-generate` prints `"allowed": true`; check it before acting, else mark handled and do nothing): SKILL.md, "Generate for me" |
| build | `action` `build:fix:<kind>:<row id>` (`{"check": [cells]}`) | fix that FAIL row of that QA output |
| review | `edit` `review:changes` (`[{"text", "timeline", "mode": "inplace" \| "new"}]`) | the editor's change list for this round |
| review | `action` `review:done` | the editor is happy: go to captions |
| captions | `answer` `captions:who` (early); `action` `captions:auto-done`; `action` `captions:add` (value: timelines; only while no gate asks `timelines`, which the button answers instead) | who adds captions; auto-caption is done; the timelines to caption (the default for the `timelines` gate, confirmed there with `capcut_closed`) |
| music | `answer` `music:source` (early); `upload` `music:<file>` (+ early `music:upload`) | Suno or own track; the track in `music/` |
| export | `action` `export:learn` | the editor exported: run the learning step |
| export | `answer` `learn:<id>` (`{"decision": "save" \| "decline", "scope": "general" \| "client"}`) | one learning proposal: `learn.py save` (with `--client` for `client`) or `learn.py decline` |

**Got flagged** (a `…:flagged` action; the site blocked the prompt, often with a vague reason, and may still have used the credits): rewrite only that prompt in safer words (same shot, same timing; follow the `.claude/edit-mo-to/safe-words.json` hints and the contract's "Safe wording"; the editor's note says what the site objected to). Show the old and the new prompt in chat. Store it the same way as the original: a prompt row: edit that prompt in `prompts2.json`, add `"note": "rewritten after a flag"` to it, re-run `plan_tools.py prompts` and `check-prompts`, then `job.py output … prompts <kind> --from prompts` (the row shows the note); a storyboard card: the beat's `prompt` in `storyboard.json`, `status` `"changed"`. Log `.claude/edit-mo-to/run gui/job.py log "<folder>" "[<step>] Rewrote Shot N after a flag"` (the shot in words), mark the event handled, and write the trigger (the flagged words, the site's message and the rewrite) in `{tmp}/reports/<job>/notes.txt` so the learning step proposes it as a rule. Never regenerate by itself: the editor generates the new prompt.

### Outputs the pages read
`job.py output "<folder>" <step> <kind> --file data.json` (checklist, script, or a table `{"title", "columns", "rows": [{"id", "cells": [strings, one per column], "status"?, "note"?}]}`; `status` is `ok | wait | you | err | opt | mute`), or `--from <adapter> <tool output>` (`timings`, `cuts`, `qa`, `clips`, `prompts`). Store each deliverable when you show it in chat:
- Brief checklist: `.claude/edit-mo-to/run gui/job.py output "<folder>" brief checklist --file checklist.json`, with `{"style", "language", "rules": [{"n", "rule", "source", "status": "confirmed|open|question|missing|conflict"}], "questions": [{"id", "text", "why"}]}`.
- Script: `.claude/edit-mo-to/run gui/job.py output "<folder>" script script --file script.json`, with `{"lang": "es", "temp_en": true, "lines": [{"id": "H1", "text": "…", "en": "…"}]}` (`en` only with TEMP_EN). Script QA: `.claude/edit-mo-to/run gui/job.py output "<folder>" script qa --from qa <qa json>`.
- Storyboard: no output; the GUI reads `<folder>/storyboard/storyboard.json` and the `SB-n` / `CHAR-n` images directly.
- Older VO: `.claude/edit-mo-to/run gui/job.py output "<folder>" voiceover oldvo --file oldvo.json` (a table, one row per sentence, `id` = the sentence number, cells time and text).
- Timings: `.claude/edit-mo-to/run gui/job.py output "<folder>" timing timings --from timings "{tmp}/reports/<job>/timings.json"`.
- Cuts: `.claude/edit-mo-to/run gui/job.py output "<folder>" timing cuts --from cuts "{tmp}/cuts/<name>.cuts.json"`.
- Prompts: `.claude/edit-mo-to/run gui/job.py output "<folder>" prompts prompts --from prompts "{tmp}/reports/<job>/prompts2.json"` (one per timeline: kind `prompts-t02` etc.; every kind starting with `prompts` shows). Prompt QA: `… output "<folder>" prompts qa --from qa <qa json>`.
- Clips: `.claude/edit-mo-to/run gui/job.py output "<folder>" clips clips --from clips "<qc report.json>"`.
- QA: `.claude/edit-mo-to/run gui/job.py output "<folder>" build qa --from qa "{tmp}/reports/<job>/qa_check.json"` (per timeline `qa-t02` etc.; every kind starting with `qa` shows on Build & QA).
- Review: `.claude/edit-mo-to/run gui/job.py output "<folder>" review changes --file changes.json` (columns Change, Timeline, In place / new, Status) and, from `edit_diff`, `… output "<folder>" review edits --file edits.json`.
- Captions: `.claude/edit-mo-to/run gui/job.py output "<folder>" captions qa --from qa "<qa_captions json>"`.
- Music: `.claude/edit-mo-to/run gui/job.py output "<folder>" music suno --file suno.json`, one row per part of at most 18 s; every row carries a `prompt` field with the full Suno prompt (the page shows Copy only when `prompt` is set), cells such as length and crossfade note.
- Learning: `.claude/edit-mo-to/run gui/job.py output "<folder>" export learn --file learn.json`, one row per proposal (`id`, cells rule, section, why).

Card fields the pages read: `client`, `product`, `folder`, `style`, `language`, `temp_en` (`on | partial:<names> | removed | off`), `timelines` (`a|b|c`), `broll_source`, `generator` (`Higgsfield · <model label>` or `Google Flow`; an old `Seedance` reads as Higgsfield · Seedance 2.0), `clips_folder`, `project`, e.g. `.claude/edit-mo-to/run gui/job.py card "<folder>" "style=UGC selfie review" "temp_en=on" "timelines=Hook 1|Hook 2"`.
