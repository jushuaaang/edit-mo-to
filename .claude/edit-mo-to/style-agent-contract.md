# Style agent contract (shared by ugc, broll, claymation, pixar, product-ad)

## What you receive (in the dispatch prompt)
- `mode`: `prompts` or `edit-plan`
- `client` (matches a file in `D:\Video Editing\.claude\edit-mo-to\clients\` if one exists) and the `product` name
- `video_folder`: the per-video folder the user made (clips, VO and music live here)
- `brief_checklist`: every rule from the client brief, each one quoted
- `script`: the approved script, one line per row, with hook/body/CTA labels (or "none — music only")
- `vo_timings`: table from `media_timing.py vo` (line, start_sf, end_sf, duration), or `beats` for product ads
- `broll_source`: `client` | `ai` | `both`
- `generator`: `google-flow` | `seedance` (only when AI clips are needed)
- `client_broll_folder`: path, if any
- `clips`: inventory of available clips (path, duration, fps), when they exist
- `revision`: change requests plus the timeline they apply to (edit-plan mode only, optional)

## Before you write anything
1. Read `D:\Video Editing\.claude\edit-mo-to\preferences.md`: the General section, your style's section, the generator's section and "Known generation failures". These are the user's own rules. Follow them.
2. Read the client file, if there is one.
3. If a brief rule conflicts with a preference, **the brief wins**. Say so in your notes.

## Shared rules
- Default 9:16 (1080×1920), 30 fps, unless the brief says otherwise.
- Times shown to the user are `seconds:frames` at 30 fps (`7:12`). Past 60s use `m:ss:ff`.
- Every AI clip's length equals the VO span it covers, from `vo_timings`. Dialogue is quoted word for word, with its in/out times.
- Never use a clip twice in one timeline, and don't reuse hook clips across hooks.
- Never put captions or subtitles in prompts or plans. The user adds captions in CapCut. Badges, CTA graphics, stats, callouts and other motion graphics go in the edit plan's `overlays` (see below), and only if the brief or style calls for them or they make the edit more engaging without adding claims.
- Every AI prompt repeats the user's lock lines (realism / product / no-text / voice / look / style bible, whichever apply). Never write "same as above".
- Use absolute Windows paths, with the full folder address.
- **Paths:** check that every path you're given exists. If `client_broll_folder` is missing, look for it inside `video_folder` (e.g. `D:\Video Editing\<client>\…`), use what you find, and say so in Notes.
- **Cataloguing client clips** (libraries can hold 900+ files):
  1. List the whole tree with folder names. Shortlist candidates by folder plus filename against each line.
  2. For the shortlist only (roughly ≤ 30 clips), run ffprobe (`ffprobe -v error -show_entries format=duration:stream=r_frame_rate,width,height:stream_side_data=rotation -of json "<file>"`).
  3. Make one contact strip per clip: `ffmpeg -v error -i "<file>" -vf "fps=1/max(1\,floor(<dur>/6)),scale=180:-1,tile=6x1" -frames:v 1 "C:\Users\Keytech\mcp-servers\tmp\frames\<n>.jpg"`. Read it, and judge from what you see, never from the filename alone.
  - ffmpeg auto-applies rotation, so frames look upright. Still note clips with rotation metadata so the user can check them in CapCut.
- **Already-generated AI clips** in the video folder or client library from earlier jobs count as usable library footage.
- **Splitting lines into several cuts:** use the word timestamps in `vo_timings.words` to place cut points between words. Never guess.
- **AI clip shorter than the generator's minimum** (e.g. a 1.5s span with Flow's 4s minimum): generate the minimum and say "use the first N:FF" (or which part to keep).
- **Writing AI prompts:** the user already chose `broll_source` at a gate. With `client`, write no AI prompts. With `both`, write prompts only for lines where no client clip fits. Extra "optional upgrade" prompts must be clearly marked OPTIONAL and kept to 2 at most.

## Output: `mode: prompts`
A short intro line, then one table:

`# | Script line | VO in | VO out | Length | Source | Prompt / Cut | Attach`

- This table layout is the standard. For split or grid shots, put the slot first in Source (`TOP: <path>`, `BOTTOM: <path>`, `GRID 2/4: <path>`).
- Give cuts at the clip's own fps and say which fps, if it isn't 30.
- **Source** is either the full path of a client clip (with **Cut** = source in–out in `seconds:frames`), or `AI-n (generate)`.
- Under the table, each AI prompt goes in its own fenced code block (`AI-n`), so it's easy to copy.
- End with "Notes": brief rules applied, conflicts, and anything the user must decide.

## Output: `mode: edit-plan`
1. A readable table: `# | Timeline | At | Len | File | Src in–out | Speed | Layout | Transition/Effect | Line`.
2. One fenced ```json block, which the editor agent consumes:

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

- **Overlays (preferred for all on-screen graphics).** These are animated, transparent HyperFrames overlays: badges, CTA buttons, end cards, stats, one-word pops, product callouts, hook numbers, split labels.
  - Pick templates from `D:\Video Editing\.claude\edit-mo-to\motion\CATALOGUE.md`. The editor renders each one to a `.mov` during the build and places it on a top track at `at`. Add `"track": "ui" | "title" | "flash"` to layer them.
  - **Sound design (SFX):** each overlay can carry `"sfx": "default"` (the template's tuned cue from `motion\sfx_defaults.json`: whoosh on flashes and titles, pop on cards and badges, ping on ✓ and stats, click on buttons), `"none"`, or a custom list `[{"name": "sparkle", "offset": 0.1, "len": 1.0, "volume": 0.3}]` using the 19 sounds in `motion\sfx\`.
    - Use `"default"` on every overlay in the Apple-UI talking-head style, and on key overlays (badge, CTA, end card, stat, word-pop) in other styles. Use `"none"` where the brief bans SFX, or for calm or luxury moods.
    - Cues are placed on sound tracks under the VO, trimmed, with stacked whooshes merged. This is separate from music, which stays the user's choice at step 11.
  - If no template fits, put the need in Notes ("needs new template: countdown timer") rather than inventing a template name. The skill then asks the `motion-designer` to create it.
  - `duration` becomes the rendered length, and also the template's `duration` var.
  - `vars` override template defaults. To see each template's variables, run `motion_render.py list`.
  - Use the client's colours and fonts (Google Fonts names) from the client file or brief.
  - Every text is a claim, so use only claims the brief or product page supports.
  - Keep overlays clear of faces and of the product's label, and leave the bottom ~400px free for the user's captions (except CTA/end-card at the very end).
  - `texts` (plain CapCut text) is a fallback only.
- **VO per timeline.** The VO is not sliced into files; one ElevenLabs file may hold hooks and body.
  - Each timeline takes only its span of the VO: `vo_in`/`vo_out` are **source seconds in the VO file** (from `vo_timings`). The editor places that span at timeline 0.
  - So a clip's `at` is relative to the timeline start: `at = line_start_in_vo - vo_in`.
  - If the user sends separate VO files per hook, set `vo` per timeline, with `vo_in` 0 and `vo_out` the file length.
  - `music_volume` 0.1 is about −20 dB under the VO; use 0.6–1.0 for music-only product ads.
- All times are in seconds (floats). Write timeline times (`at`, and clip ends) as exact frame multiples n/30 with 10 decimals (e.g. 3.5666666667, not 3.5667); 4-decimal rounding made clips overlap by 0.1µs and VectCutAPI refused them. `at` is the timeline position. Source duration = `(src_out - src_in)`; on the timeline it lasts `(src_out - src_in)/speed`.
- Split screen: use tracks `video_top` and `video_bottom`, with `y` = +0.5 (top) / -0.5 (bottom), and add `"layout":"split-top"` / `"split-bottom"`. x/y are in units of **half the canvas**, the same as VectCutAPI `transform_x/y`, and +y is up.
  - A 9:16 source is 1920 tall, so each pane must be cropped to 1080×960. The editor does this with `add_video`'s mask parameters. If that fails, it adds a `manual` note.
  - Grids use `scale` 0.5 (2×2: x/y ±0.5) or 0.333 (3×3: x/y 0, ±0.667), with `"layout":"grid"`. Grid cells are scaled, not masked, so 9:16 sources fill their cell exactly.
- Hooks: each hook is its own timeline ("Timeline 02 – Hook 1", "Timeline 03 – Hook 2"…). Timeline 01 is the body plus CTA.
- Clip audio: `mute: true` when VO plays over it. Keep it only for lip-synced A-roll when no separate VO is placed under that clip.
- `manual`: anything the CapCut tools can't do (mirroring, special effects not in the list). The editor passes these on to the user.
