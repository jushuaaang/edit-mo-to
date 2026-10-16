# edit-mo-to: step detail

## Reading briefs (step 2)
- **PDF:** use the Read tool (pages param for long files). **.docx:** `python -c "import zipfile,re;x=zipfile.ZipFile(r'<f>').read('word/document.xml').decode();print(re.sub(r'<w:p[^>]*>','\n',re.sub(r'<(?!w:p)[^>]+>','',x)))"`, or ask the user to paste it if that fails.
- **Notion:** public pages via WebFetch, one call per page, and follow links to sub-pages the brief points to (checklists, examples). If a page needs login or returns nothing, ⛔ ask the user to paste or export it. The Notion connector isn't authorised.
- **Reference videos:**
  - `ffprobe` for duration, fps and size;
  - a contact sheet (`ffmpeg -i "<v>" -vf "fps=1,scale=240:-1,tile=6x5" -frames:v 1 "C:\Users\Keytech\mcp-servers\tmp\ref_sheet.jpg"`), which you then Read;
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
mode: prompts | edit-plan
client: <client file stem or "new">   product: <Product>
video_folder: <path>
brief_checklist: <the table>
script: <numbered lines with Hook/Body/CTA labels>
vo_timings: <lines table + the words list from media_timing vo>  (or beats for product ads)
broll_source: client | ai | both     generator: google-flow | seedance
vo: <path(s): one file, or one per hook/body>   music: <path or none>   (product ads: music is required)
client_broll_folder: <path or none>   (check that it exists before dispatching)
clips: <inventory: path | duration | fps>   (edit-plan mode)
revision: <requests + target timeline>      (review loop only)
```

## Dispatch template (editor)
```
action: build | revise-new-timeline | revise-in-place | add-music
plan: <edit-plan JSON from the style agent>   (not needed for add-music)
music: <path>   music_volume: 0.1   timelines: [<names>]   (add-music only)
project: <Product>   timeline: <name>   new_timeline_name: <name>
import_files: <every clip, VO, music, B-roll file the user gave for this video>   (build)
```

## Dispatch template (qa)
```
gate: script | prompts | build
style: <style>   client: <client>
brief_checklist / script / vo_timings: <as above>
prompts: <style agent output>          (prompts gate)
plan + project folder + timelines:     (build gate)
```

## Gate wording (keep it short, one question per message)
- Brief: "Send me the client's brief or instructions (PDF, doc, Notion link, or paste it), any reference videos, and the folder you made for this video."
- Checklist: "Here's everything the brief requires. Anything missing or wrong?"
- Script approval: "Approve this script, or tell me what to change."
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

When dispatching `revise-in-place`, don't ask the editor to back up first: `replace` already backs the timeline up and returns the path (an extra request makes two backups).
