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
broll_source: client | ai | both     generator: google-flow | seedance
vo: <path(s): one file, or one per hook/body>   music: <path or none>   (product ads: music is required; others: none until step 11)
client_broll_folder: <path or none>   (check that it exists before dispatching)
inventory: {tmp}/reports/<job>/inv/inventory.json, or one inv_<subfolder>/inventory.json per shortlisted subfolder of a big library   (when client B-roll exists)
revision: <requests + target timeline>      (review loop only)
aroll_cuts: <keep.json path(s) from speech_cuts.py>   (talking-head A-roll only)
```

## Dispatch template (editor)
```
action: build | revise-new-timeline | revise-in-place | add-music
job: <Product, no spaces>   project: <Product>
plan: {tmp}/reports/<job>/plan.json   (build, revise-new-timeline; add-music: the built plan copy <base>/.edit-mo-to/built/<timeline>.plan.json)
import_files: <every clip, VO, music, B-roll file the user gave for this video>   (build)
timeline: <name>   new_timeline_name: <name>   (revisions)
old_plan: <base>/.edit-mo-to/built/<timeline>.plan.json   new_plan: {tmp}/reports/<job>/plan.json (re-expanded)   (revise-in-place)
segments: <capcut_project segments dump of the timeline>   (revise-in-place, optional: the editor makes it)
music: <path>   music_volume: 0.1   timelines: [<names>]   (add-music only)
client: <client>   video: <video name>   (for the hand-edit log)
```

## Dispatch template (qa)
```
gate: script | prompts | build
style: <style>   client: <client>   job: <Product, no spaces>
pack / brief_checklist / script / script_file / timings_compact / timings / limits: <as above>
prompts: <prompts2.json + prompts.txt paths>          (prompts gate)
plan: <plan.json path; a revise-new-timeline timeline: its built plan copy <base>/.edit-mo-to/built/<new name>.plan.json>   project: {capcut_drafts}/<Product>   timelines: <names>   client_folder: <path>   (build gate)
qa_check: {tmp}/reports/<job>/qa_check.json   (build gate, when the skill ran qa_check.py)
scope: full | delta   changed: <clip #s per timeline, ovN / prompt ids / ops since the last QA>   (delta after a small fix)
```

## Gate wording (keep it short, one question per message)
- Brief: "Send me the client's brief or instructions (PDF, doc, Notion link, or paste it), any reference videos, and the folder you made for this video."
- Checklist: "Here's everything the brief requires. Anything missing or wrong?"
- Script approval: "Approve this script, or tell me what to change."
- Storyboard: "Want a storyboard first, so you see my direction before any video is made? (Recommended for new clients and AI-heavy ads.)"
- Character sheet: "Generate the character sheet from this prompt and send it to me (or tell me when it's saved)."
- Keyframes: "Now generate the storyboard images from these prompts and tell me when they're saved in <folder>/storyboard/."
- Storyboard approval: "Here's the full storyboard built from your images. Approve this direction, or tell me what to change."
- VO: "Generate the voiceover in ElevenLabs and send me the file."
- B-roll source: "Use the client's B-roll, generate AI videos, or both?"
- Generator: "Where will you generate: Seedance or Google Flow?"
- Clips ready: "Tell me when all the clips are generated and in <folder>."
- Review: "Which timeline is this change for? And should I make a new timeline for it, or work directly in that timeline (I'll back it up first)?"
- Quit CapCut: "Please quit CapCut completely before I write to the project, and tell me when it's closed."
- Captions: "Run auto-caption in CapCut and tell me when it's done."
- Music: "Do you want a Suno prompt from me, or will you find no-copyright YouTube music?"

## Revision requests
Turn each request into: target timeline, mode (new or in place), new timeline name ("Timeline 0N – <Hook/Body> rev k"), and the exact changes (clip #, what to swap, new times). Pass these to the style agent as `revision`. Small timing or swap changes don't need new prompts unless new AI clips are required. If they are, go back to step 6 for just those clips.

When dispatching `revise-in-place`, don't ask the editor to back up first: `replace` and `patch` already back the timeline up and return the path (an extra request makes two backups). Pass `old_plan` = `<base>/.edit-mo-to/built/<timeline>.plan.json` (what the timeline was last built or patched from; `build_project` writes it, and the editor refreshes it with `mark-built` after each patch) and `new_plan` = the re-expanded `plan.json`. Expand always overwrites `plan.json`, so it can never be the old plan: small timing, swap and scale changes then go in as `patch` ops, keeping the user's edits. A job built before the built plan copy existed has none: the editor seeds it from the plan the timeline was built from (`mark-built`), or falls back to `revise-new-timeline` / `replace` (editor.md).
