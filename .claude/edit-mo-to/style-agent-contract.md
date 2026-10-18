# Style agent contract (shared by ugc, broll, claymation, pixar, product-ad)

## What you receive (in the dispatch prompt)
- `mode`: `prompts` | `edit-plan`
- `client` (a file in `{root}/.claude/edit-mo-to/clients/`, if one exists) and `product`
- `video_folder`: the per-video folder (clips, VO, music)
- `brief_checklist`: every brief rule, quoted
- `script`: approved script, one line per row, labelled hook/body/CTA (or "none — music only")
- `vo_timings`: `media_timing.py vo` table (line, start_sf, end_sf, duration, plus `words`), or `beats` for product ads
- `broll_source`: `client` | `ai` | `both`; `generator`: `google-flow` | `seedance` (only when AI clips are needed)
- `client_broll_folder` (if any); `clips`: inventory (path, duration, fps), when they exist
- `revision`: change requests + target timeline (edit-plan only, optional)
- `aroll_cuts`: path(s) to `speech_cuts.py` `keep.json` files (talking-head A-roll with its own audio, optional). Its `segs` are that clip's A-roll in order: one plan clip each (same file, `src_in`/`src_out`/`at`, not muted), already back to back and frame-exact. Never re-cut inside them. Its re-timed `words`/`lines` are the timing for everything over that A-roll (B-roll, overlays, punch-ins).

## Before you write anything
1. Read `{root}/.claude/edit-mo-to/preferences.md`: General, your style's section, the generator's section, and "Known generation failures". Follow them.
2. Read the client file, if there is one.
3. If a brief rule conflicts with a preference, **the brief wins**; say so in Notes.

## Shared rules
- 9:16 (1080×1920), 30 fps unless the brief says otherwise. Times shown to the user are `seconds:frames` (`7:12`); past 60s, `m:ss:ff`.
- Every AI clip's length = the VO span it covers (from `vo_timings`); dialogue quoted word for word with in/out times.
- Never use a clip twice in a timeline, and don't reuse hook clips across hooks.
- No captions or subtitles in prompts or plans. Motion graphics go in the plan's `overlays` (below), only if the brief or style calls for them or they add engagement without adding claims.
- Every AI prompt repeats the applicable lock lines (realism / product / no-text / voice / look / style bible) in full. Never "same as above".
- Absolute Windows paths with the full folder address. Check every given path exists; if `client_broll_folder` is missing, look inside `video_folder` (e.g. `{root}/<client>/…`), use what you find, and say so in Notes.
- **Cataloguing client clips** (libraries can hold 900+ files):
  1. List the whole tree with folder names; shortlist by folder + filename against each line.
  2. ffprobe the shortlist only (≤ ~30): `ffprobe -v error -show_entries format=duration:stream=r_frame_rate,width,height:stream_side_data=rotation -of json "<file>"`.
  3. One contact strip per clip: `ffmpeg -v error -i "<file>" -vf "fps=1/max(1\,floor(<dur>/6)),scale=180:-1,tile=6x1" -frames:v 1 "{tmp}/frames/<n>.jpg"`. Read it and judge by what you see, never the filename alone. ffmpeg auto-rotates, so also note clips with rotation metadata for the user to check in CapCut.
- AI clips already generated in earlier jobs count as library footage.
- **Splitting a line into several cuts:** place cut points between words using `vo_timings.words`. Never guess.
- **AI clip shorter than the generator's minimum** (e.g. 1.5s vs Flow's 4s): generate the minimum and say "use the first N:FF" (or which part).
- **AI prompts follow `broll_source`:** `client` = none; `both` = only for lines no client clip fits. "Optional upgrade" prompts are marked OPTIONAL, 2 at most.

## Output: `mode: prompts`
A short intro line, then one table: `# | Script line | VO in | VO out | Length | Source | Prompt / Cut | Attach`
- **Source** = the client clip's full path (with **Cut** = source in–out in `seconds:frames` at the clip's own fps, stated if not 30), or `AI-n (generate)`. Split or grid shots put the slot first (`TOP: <path>`, `BOTTOM: <path>`, `GRID 2/4: <path>`).
- Each AI prompt goes under the table in its own fenced code block (`AI-n`).
- End with "Notes": brief rules applied, conflicts, decisions for the user.

## Output: `mode: edit-plan`
1. A table: `# | Timeline | At | Len | File | Src in–out | Speed | Layout | Transition/Effect | Line`.
2. One fenced ```json block for the editor:

```json
{"project":"<Product>","fps":30,"width":1080,"height":1920,
 "timelines":[{"name":"Timeline 01 – Body+CTA","vo":"<abs path|null>","vo_in":0.0,"vo_out":42.3,"vo_volume":1.0,
   "music":"<abs path|null>","music_volume":0.1,
   "clips":[{"file":"<abs path>","src_in":0.0,"src_out":3.2,"at":0.0,"speed":1.0,"track":"video_main",
             "x":0.0,"y":0.0,"scale":1.0,"transition":null,"effect":null,"mute":true,"line":"<script line>"}],
   "overlays":[{"template":"badge","vars":{"accent":"100%","text":"MONEY-BACK","bg":"#1d3fbf"},"at":12.0,"duration":3.0,"why":"guarantee line"}],
   "texts":[],
   "manual":["Mirror clip 4 (flag reads backwards)"]}]}
```

- **Overlays** (preferred for all on-screen graphics: badges, CTA buttons, end cards, stats, word pops, callouts, hook numbers, split labels): animated transparent HyperFrames overlays.
  - Templates from `{root}/.claude/edit-mo-to/motion/CATALOGUE.md`; `motion_render.py list` shows each one's vars. `vars` override defaults. The editor renders each to a `.mov` during the build and places it at `at`; add `"track": "ui" | "title" | "flash"` to layer them. `duration` is the rendered length and the template's `duration` var.
  - **SFX:** `"sfx": "default"` (the template's tuned cue from `motion\sfx_defaults.json`), `"none"`, or a custom list `[{"name": "sparkle", "offset": 0.1, "len": 1.0, "volume": 0.3}]` from the 19 sounds in `motion\sfx\`. Use `"default"` on every overlay in the Apple-UI talking-head style and on key overlays (badge, CTA, end card, stat, word-pop) elsewhere; `"none"` where the brief bans SFX or for calm/luxury moods. Cues land on sound tracks under the VO; music stays the user's choice at step 11.
  - If no template fits, write the need in Notes ("needs new template: countdown timer"); never invent a template name. The skill asks `motion-designer`.
  - Client colours and fonts (Google Fonts names) from the client file or brief. Every text is a claim: only brief- or product-page-supported claims.
  - Each overlay's `at` lands on a video cut (a clip's `at`), exact to the frame, so it and its SFX hit with the cut.
  - Keep clear of faces and the product label, and leave the bottom ~400px free for captions (except CTA/end card at the very end).
  - `texts` (plain CapCut text) is a fallback only.
- **VO per timeline:** one ElevenLabs file may hold hooks and body; it isn't sliced. `vo_in`/`vo_out` are **source seconds in the VO file**; the editor places that span at timeline 0, so `at = line_start_in_vo - vo_in`. Separate VO files per hook: set `vo` per timeline, `vo_in` 0, `vo_out` = file length.
- `music_volume` 0.1 ≈ −20 dB under the VO; 0.6–1.0 for music-only product ads.
- Times are float seconds. Timeline times (`at`, clip ends) are exact n/30 with 10 decimals (3.5666666667, not 3.5667); 4-decimal rounding caused overlaps VectCutAPI refused. Timeline length = `(src_out - src_in)/speed`.
- **Split screen:** tracks `video_top`/`video_bottom`, `y` +0.5/−0.5, `"layout":"split-top"`/`"split-bottom"`. x/y are in half-canvas units (VectCutAPI `transform_x/y`), +y up. Each 9:16 pane is cropped to 1080×960 by the editor's mask; if that fails it adds a `manual` note.
- **Grids:** `scale` 0.5 (2×2, x/y ±0.5) or 0.333 (3×3, x/y 0, ±0.667), `"layout":"grid"`; scaled, not masked.
- **Hooks:** Timeline 01 = hook 1 + body + CTA. Each other hook is its own hook-only timeline ("Timeline 02 – Hook 2", "Timeline 03 – Hook 3", …); the user pastes T01's body in after it.
- **Clip audio:** `mute: true` under VO; keep it only for lip-synced A-roll with no VO under that clip.
- `manual`: anything the tools can't do (mirroring, effects not in the list); the editor passes it to the user.

## Hand-back (all style agents)
- Final message ≤ ~30 lines: what you produced, brief rules you couldn't meet (with the exact fix), decisions for the user.
- Write the full output to `{tmp}/reports/<job>/` (`<job>` = product name, no spaces): `prompts.txt` (table + prompt blocks) in `prompts` mode; `plan.json` + `plan_table.txt` in `edit-plan` mode. Give the paths instead of pasting. This changes where the output goes, not what it contains.
- **Re-runs for a fix:** rewrite only the changed rows and prompts, listed by #, with one line on what changed in each.
