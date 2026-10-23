# Style agent contract (shared by ugc, broll, claymation, pixar, product-ad)

## What you receive (in the dispatch prompt)
- `mode`: `storyboard` | `prompts` | `edit-plan`
- `pack`: the context pack for this job and style (`{tmp}/reports/<job>/pack_<style>.md`, written by `context_pack.py`): the rules from `preferences.md` and `my-preferences.md` you need, plus the client file
- `client` (a file in `{root}/.claude/edit-mo-to/clients/`, if one exists) and `product`
- `video_folder`: the per-video folder (clips, VO, music)
- `brief_checklist`: every brief rule, quoted
- `script`: approved script, one line per row, labelled hook/body/CTA (or "none — music only"); `script_file`: the same lines in a txt, one per line (for `plan_tools.py`)
- `timings_compact` (the `vo_timings` the rules below read): `media_timing.py vo --compact` text (`# lines` as `n|start_sf|end_sf|matched|text`, `# words` as `word|start_f|end_f` in frames), or `beats` for product ads
- `timings`: the `media_timing.py vo` JSON file of the same VO, for the tools' `--timings` (they read JSON only)
- `broll_source`: `client` | `ai` | `both`; `generator`: `google-flow` | `seedance` (only when AI clips are needed)
- `client_broll_folder` (if any); `inventory`: `{tmp}/reports/<job>/inv/inventory.json` (every clip's path, duration, fps, width, height, rotation and 6-frame strip, plus contact sheets), when client clips exist; `clips`: older inline inventory (path, duration, fps)
- `limits`: `{tmp}/reports/<job>/limits.json` (`min_s`, `max_s`, `caption_band_px`, `no_text`, only the keys the brief fixes), when given
- `revision`: change requests + target timeline (edit-plan only, optional)
- `aroll_cuts`: path(s) to `speech_cuts.py` `keep.json` files (talking-head A-roll with its own audio, optional). Its `segs` are that clip's A-roll in order: one plan clip each (same file, `src_in`/`src_out`/`at`, not muted), already back to back and frame-exact. Never re-cut inside them. Its re-timed `words`/`lines` are the timing for everything over that A-roll (B-roll, overlays, punch-ins).

## Before you write anything
1. Read the one file `pack` names (`{tmp}/reports/<job>/pack_<style>.md`): General, your style's section, the generator's section and "Known generation failures" from `preferences.md` (shared starter rules), then the same from `my-preferences.md` (this editor's own rules; **they win on conflict**), then the client file. Follow them. Don't read `preferences.md` or `my-preferences.md` yourself. No `pack` in the dispatch: read those files as the pack would (the sections above).
2. Read the client file only if the pack has no Client section (and a client file exists).
3. If a brief rule conflicts with a preference, **the brief wins** (over the pack too); say so in Notes.
4. If the dispatch names `inventory`, use its clips and strips; never ffprobe or render strips for clips already in it.

## Shared rules
- 9:16 (1080×1920), 30 fps unless the brief says otherwise. Times shown to the user are `seconds:frames` (`7:12`); past 60s, `m:ss:ff`.
- Every AI clip's length = the VO span it covers (from `vo_timings`); dialogue quoted word for word with in/out times.
- Never use a clip twice in a timeline, and don't reuse hook clips across hooks.
- No captions or subtitles in prompts or plans. Motion graphics go in the plan's `overlays` (below), only if the brief or style calls for them or they add engagement without adding claims.
- Every AI prompt carries the applicable lock lines (realism / product / no-text / voice / look / style bible) in full. In `prompts2.json` you write each lock once in `locks` and list it per prompt; `plan_tools.py prompts` writes it out in full in every prompt. Never "same as above", never a shortened lock.
- Absolute Windows paths with the full folder address. Check every given path exists; if `client_broll_folder` is missing, look inside `video_folder` (e.g. `{root}/<client>/…`), use what you find, and say so in Notes.
- **Cataloguing client clips** (libraries can hold 900+ files):
  1. With `inventory`: its clips (duration, fps, size, rotation) and strips are the catalogue. Read the contact sheets (6 strips each) and judge by what you see, never the filename alone. Probe or strip only clips that are not in it.
  2. Without it (or for clips outside it): list the whole tree with folder names; shortlist by folder + filename against each line.
  3. Catalogue the shortlist only (≤ ~30): a whole shortlisted folder with `sheets.py inventory` (`"{python}" "{root}/.claude/edit-mo-to/tools/sheets.py" inventory "<folder>" "{tmp}/reports/<job>/inv_<name>" [--max N]`), or single files with `ffprobe -v error -show_entries format=duration:stream=r_frame_rate,width,height:stream_side_data=rotation -of json "<file>"` and one contact strip each: `ffmpeg -v error -i "<file>" -vf "fps=1/max(1\,floor(<dur>/6)),scale=180:-1,tile=6x1" -frames:v 1 "{tmp}/frames/<n>.jpg"`. Read the strips and judge by what you see. ffmpeg auto-rotates, so also note clips with rotation metadata for the user to check in CapCut.
- AI clips already generated in earlier jobs count as library footage.
- **Splitting a line into several cuts:** place cut points between words using the `vo_timings` words. Never guess.
- **AI clip shorter than the generator's minimum** (e.g. 1.5s vs Flow's 4s): generate the minimum and say "use the first N:FF" (or which part).
- **AI prompts follow `broll_source`:** `client` = none; `both` = only for lines no client clip fits. "Optional upgrade" prompts are marked OPTIONAL, 2 at most.
- **Tools** run as `"{python}" "{root}/.claude/edit-mo-to/tools/plan_tools.py" …`. Output files go in `{tmp}/reports/<job>/` (`<job>` = product name, no spaces).

## Output: `mode: storyboard` (script gate, before any video is generated)
Two phases, in this order. The orchestrator passes `phase`. No VO exists yet, so `est` times come from the script (about 2.5 words/s). **Every prompt is pasted in chat in its own code block (never only in a file).**
**Phase `prompts` (images first):**
1. **Character first.** For a character-driven ad (always Pixar / claymation; any ad with a recurring person or mascot) give a **character sheet prompt** per recurring character: front / side / back / 3/4 view plus 3–4 expressions on a plain background, wardrobe down to the buttons, with the style bible. Pixar: this is required. Hand back only these first and stop; the keyframe prompts come after the sheet is approved.
2. **Then the keyframe prompts** (Nano Banana or the editor's image generator), one per beat, named `SB-1…`, each written as the exact first frame of its clip, with the lock lines that apply (realism, product, look, wardrobe, no text) and a note to attach the character sheet(s) as references. Table in chat: `# | Script line | Shot | Save as`, prompts in code blocks beneath.
**Phase `board` (only after the images are saved):**
3. Look at the saved sheet and keyframes. Write `<video_folder>/storyboard/storyboard.json` in the schema of `tools/storyboard.py`: `title`; `direction` (2–3 lines: hook idea, pacing, look); brand `font`/`bg`/`fg`/`accent`; one beat per script line or planned cut, with `line`, `est`, `shot` (a real client clip and time when one fits, otherwise an AI shot with framing / subject / action / camera), the saved keyframe (`storyboard/SB-n.png`, picked up automatically by `storyboard.py`; the character sheet is saved there as `CHAR-1.png`, for reference only), `graphic` (a CATALOGUE template, only where the edit will really have one), `transition` and `note` (mood, music, SFX).
4. Run `"{python}" "{root}/.claude/edit-mo-to/tools/storyboard.py" "<video_folder>/storyboard/storyboard.json"` and hand back the `storyboard.html` path and a one-table summary of the beats.

## Output: `mode: prompts`
Write `{tmp}/reports/<job>/prompts2.json` (the compact prompt spec), expand it, check it, fix until clean. Never type `prompts.txt` yourself.

```json
{"style": "ugc", "generator": "google-flow", "product": "Nativia", "aspect": "9:16",
 "attach": {"@Image1": "D:/Video Editing/Nativia/refs/R1_headshot.png", "@Image2": "D:/Video Editing/Nativia/refs/product.png"},
 "locks": {"realism": "<full master realism line>", "product": "<full product lock>", "notext": "No subtitles, no captions, no on-screen text.",
           "voice": "<full voice lock>", "look": "<full look lock>", "pacing": "Her mouth movement matches this pacing exactly."},
 "prompts": [{"id": "AI-3", "line": 3, "vo_in_f": 72, "vo_out_f": 180, "gen_len_s": 4, "use": "0:00-3:18",
              "setting": "...", "subject": "...", "action": "0.0–2.5s: she lifts the jar and says: \"...\"", "camera": "...",
              "dialogue": "<the words of line 3 she says, verbatim>", "attach": ["@Image1", "@Image2"],
              "locks": ["realism", "product", "notext", "voice", "look", "pacing"],
              "lock_overrides": {"product": "..."}, "negative": "...", "optional": false}],
 "notes": ["brief rule applied: ...", "decision for the user: ..."]}
```

- `style`: `ugc` | `broll` | `claymation` | `pixar` | `product-ad`. Required locks per style (`REQUIRED_LOCKS` in `plan_tools.py`): ugc = realism, product, notext, voice, look, pacing; broll = realism, notext; claymation and pixar = style_bible, notext, voice; product-ad = product, notext. Other lock names (e.g. `wardrobe`) are allowed; every listed lock needs its text in `locks` or `lock_overrides`.
- `locks`: each lock text written **once, in full, following the brief and the client** (they are your words, not a template). `lock_overrides` replaces one lock's text for one prompt (e.g. the shorter clay B-roll style line). `prompts.txt` always holds them in full; never shorten them.
- Per prompt: `id` (`AI-n`, `S1`, `C1`…), `line` (script line number), `vo_in_f`/`vo_out_f` (the line's VO span in frames, within ±2 frames of `vo_timings`), `gen_len_s` (the generated length; when it is longer than the span, `use` = the part to keep as `s:ff-s:ff`, matching the span), then only what is unique: `setting`, `subject`, `action` (second windows), `camera`, `look`, `dialogue` (only the spoken words, a verbatim part of the script line, checked against it; when `action` already quotes them in its windows, the prompt prints them only there, so the words appear once), `attach` (keys of the top-level `attach`, in order), `locks`, `negative`, `optional` (OPTIONAL upgrades). Lines covered by several rows (AI and client) must together cover the line's span, each inside it. Image prompts (character sheets, keyframes) get `"kind": "character"` or `"keyframe"` and appear in a `# | Script line | Shot | Save as` table.
- Each prompt block comes out in the fixed order Subject · Setting · Action · Camera · Look · Dialogue · Locks · Attach · Negative. Seedance video prompts start "Start on @Image1." automatically.
- Two prompts for one line need a cut point between words (the second's `vo_in_f` ≥ the first's `vo_out_f`). Flow: ≤ 7 attachments, `gen_len_s` 4–8. Seedance: `gen_len_s` ≥ 4.
- **Client clips** (`broll_source` `client`/`both`): one entry each in `prompts`, `{"id": "1", "kind": "client", "line": 3, "file": "<full path>", "in_f": 12, "out_f": 66, "vo_in_f": 240, "vo_out_f": 294}` (`in_f`/`out_f` = the cut in the clip's own frames; add `"fps": 25` when the clip isn't 30 fps; split or grid shots add `"slot": "TOP"` / `"BOTTOM"` / `"GRID 2/4"`). They become table rows in script order with the AI rows (Source = the full path, slot first; Prompt / Cut = the cut in `seconds:frames`, fps stated if not 30), with no prompt block; `check-prompts` checks their line, their VO span and that the cut's length (at the clip's fps) equals that span ±2 frames, and skips the lock, attach and generator-length rules. Product ads (no script, no VO): leave out `line` and the VO span and give `at_f` (the beat frame the clip starts on); rows then follow `at_f` order.
- `notes`: brief rules applied, conflicts, decisions for the user.

Then run:
1. `"{python}" "{root}/.claude/edit-mo-to/tools/plan_tools.py" prompts "{tmp}/reports/<job>/prompts2.json" --script "<script_file>" [--timings "<timings>"] --out "{tmp}/reports/<job>/prompts.txt"`
2. `"{python}" "{root}/.claude/edit-mo-to/tools/plan_tools.py" check-prompts "{tmp}/reports/<job>/prompts2.json" --script "<script_file>" [--timings "<timings>"]`

Fix every error and re-run both until `check-prompts` prints `ok: true`. `--timings` takes the `timings` JSON, never the compact text; leave it out when the dispatch has none (product ads: no script, so no `--script` either). Hand back both paths.

## Output: `mode: edit-plan`
Write `{tmp}/reports/<job>/plan2.json` (the compact frame plan), expand it, check it, fix until clean. **Never type `plan.json` or the table yourself.** A body shared by several timelines is written once as `blocks.BODY` and placed with `use`.

```json
{"project": "Nativia", "fps": 30, "width": 1080, "height": 1920,
 "base": "D:/Video Editing/Nativia/",
 "brand": {"font": "Inter", "bg": "#0e2f5a", "fg": "#ffffff", "accent": "#8fd3ff"},
 "vo": {"file": "voiceover/BODY.mp3", "volume": 1.0}, "music": null,
 "blocks": {"BODY": {"clips": [["clips/pour.mp4", 12, 0, 54, {"line": "It melts in seconds"}],
                               ["clips/jar.mp4", 30, 54, 66, {"scale": 1.2, "x": 0.1, "y": -0.05}]],
                     "overlays": [["badge", 54, 90, {"text": "MONEY-BACK"}, "ui", "default", {"why": "guarantee line"}]],
                     "effects": []}},
 "timelines": [
   {"name": "Timeline 01 – H1 + Body + CTA", "vo_in_f": 0, "vo_out_f": 2577,
    "seq": [{"clips": [["hooks/H1.mp4", 0, 0, 213, {"mute": false}]], "overlays": []}, {"use": "BODY", "at_f": 213}],
    "manual": ["check lip-sync in review"]}]}
```

- **Clip row:** `[file, src_in_f, at_f, len_f]` or `[file, src_in_f, at_f, len_f, opts]`, `opts` only for non-defaults: `track` (`main` | `top` | `bottom` | `overlay`), `scale`, `x`, `y`, `speed`, `mute` (default true), `transition` + `transition_f` (default 9), `effect`, `line`, `layout` (`split-top` | `split-bottom` | `grid`), `kf` = `[[t_f, scale, x, y], …]` (keyframes), `volume`, `gain_db`, `allow_scale` (scale above 2.0), `shared` (true for a source several timelines may legitimately reuse, e.g. host A-roll the hook timelines share; skips the cross-timeline reuse check). `len_f` is the timeline length; the source span is `len_f × speed`.
- **Overlay row:** `[template, at_f, len_f, vars, track, sfx]` or with a 7th `opts` (`cutout`, `on` (`word` | `beat`, for an overlay that starts on a spoken word or a beat instead of a cut), `why`, `snap`). `track` ∈ `ui` | `title` | `flash`; `sfx` ∈ `default` | `none` | a list. Brand vars (`font`, colours) are filled from `brand` when the template declares them and the row doesn't set them.
- **Effect row:** `[name, at_f, len_f]`.
- **Text row** (plain CapCut text, `texts` in a `seq` item or block, shifted like clips): `[text, at_f, len_f, style]` or with a 5th `opts` (`bg` box colour, else the brand accent; `font`). `style` ∈ `badge` | `word` | `cta` (the editor's presets).
- Files are relative to `base` (absolute allowed). Every time is a **whole frame** at 30 fps. Rows in a `use` are shifted by its `at_f`; rows in a plain `seq` item are timeline frames.
- `vo` and `music` (`{"file", "volume"}` or null) apply to every timeline; a timeline's own `vo` / `music` (same shape, or null) overrides them, so hooks recorded as separate VO files stay in one plan2.

Then run:
1. `"{python}" "{root}/.claude/edit-mo-to/tools/plan_tools.py" expand "{tmp}/reports/<job>/plan2.json" --out "{tmp}/reports/<job>/plan.json" --table "{tmp}/reports/<job>/plan_table.txt"`
2. `"{python}" "{root}/.claude/edit-mo-to/tools/plan_tools.py" check "{tmp}/reports/<job>/plan.json" [--limits "<limits>"]`

Fix `plan2.json` for every error and re-run both until `check` prints `ok: true` (it checks whole frames, main-track gaps and overlaps, source spans inside the file, reuse, VO edges in silence, overlays on cuts and not overlapping per track, templates and their vars, SFX files, scale covering the frame, timeline length, the caption band, no caption texts). Hand back the three paths and the `check` output.

Rules for the plan's content:
- **Overlays** (preferred for all on-screen graphics: badges, CTA buttons, end cards, stats, word pops, callouts, hook numbers, split labels): animated transparent HyperFrames overlays.
  - Templates from `{root}/.claude/edit-mo-to/motion/CATALOGUE.md`; `motion_render.py list` shows each one's vars. `vars` override defaults. The editor renders each to a `.mov` during the build and places it at its `at_f`; the row's `track` (`ui` | `title` | `flash`) layers them. `len_f` is the rendered length and the template's `duration` var.
  - **SFX:** `"default"` (the template's tuned cue from `motion\sfx_defaults.json`), `"none"`, or a custom list `[{"name": "sparkle", "offset": 0.1, "len": 1.0, "volume": 0.3}]` from the 19 sounds in `motion\sfx\`. Use `"default"` on every overlay in the Apple-UI talking-head style and on key overlays (badge, CTA, end card, stat, word-pop) elsewhere; `"none"` where the brief bans SFX or for calm/luxury moods. Cues land on sound tracks under the VO; music stays the user's choice at step 11.
  - If no template fits, write the need in Notes ("needs new template: countdown timer"); never invent a template name. The skill asks `motion-designer`.
  - Client colours and fonts (Google Fonts names) from the client file or brief, chosen to fit the mood, set in `brand` (or per row in `vars`). Always set the template's `font` and colour vars this way; never leave the placeholder defaults or copy a reference video's palette. Copy a reference's effects and motion, not its look.
  - `{"cutout": true}` in an overlay's opts puts the speaker in front of it (text behind you, orbit behind the head); keep those beats 1–3 s. Every text is a claim: only brief- or product-page-supported claims.
  - Each overlay's `at_f` lands on a video cut (a clip's `at_f`), exact to the frame, so it and its SFX hit with the cut.
  - Keep clear of faces and the product label, and leave the bottom ~400px free for captions (except CTA/end card at the very end).
  - `texts` (plain CapCut text rows) are a fallback only.
- **VO per timeline:** one ElevenLabs file may hold hooks and body; it isn't sliced. `vo_in_f`/`vo_out_f` are **source frames in the VO file**; the editor places that span at timeline 0, so `at_f = line_start_f_in_vo - vo_in_f`. Separate VO files per hook: set `vo` on each hook's timeline, `vo_in_f` 0, `vo_out_f` = file length.
- `music.volume` 0.1 ≈ −20 dB under the VO; 0.6–1.0 for music-only product ads.
- Times are whole frames; the expander writes the 10-decimal seconds (3.5666666667, not 3.5667) that VectCutAPI needs, so never round by hand.
- **Split screen:** `track` `top`/`bottom`, `y` +0.5/−0.5, `layout` `split-top`/`split-bottom`. x/y are in half-canvas units (VectCutAPI `transform_x/y`), +y up. Each 9:16 pane is cropped to 1080×960 by the editor's mask; if that fails it adds a `manual` note.
- **Grids:** `scale` 0.5 (2×2, x/y ±0.5) or 0.333 (3×3, x/y 0, ±0.667), `layout` `grid`; scaled, not masked.
- **Hooks:** Timeline 01 = hook 1 + body + CTA. Each other hook is its own hook-only timeline ("Timeline 02 – Hook 2", "Timeline 03 – Hook 3", …); the user pastes T01's body in after it.
- **Clip audio:** `mute` true (the default) under VO; `"mute": false` only for lip-synced A-roll with no VO under that clip.
- `manual`: anything the tools can't do (mirroring, effects not in the list); the editor passes it to the user.

### The contract plan (`plan.json`, written by `expand`; build and QA read it)
`project`, `fps`, `width`, `height`, `base`, `brand`, and `timelines[]` with `name`, `vo` (abs path or null), `vo_in`/`vo_out` (source seconds in the VO file), `vo_volume`, `music`, `music_volume`, `clips[]`, `overlays[]`, `effects[]` (when any), `texts[]`, `manual[]`.
- clip: `file` (abs), `src_in`, `src_out`, `at` (seconds, exact n/30 with 10 decimals), `speed`, `track` (`video_main` | `video_top` | `video_bottom` | `video_overlay`), `x`, `y`, `scale`, `transition`, `effect`, `mute`, plus any opts given (`line`, `layout`, `gain_db`, `volume`, `allow_scale`, `shared`, …), `transition_duration`, `keyframes` (`[{t, scale, x, y}]`) and `block` (the shared block it came from). Timeline length = `(src_out - src_in)/speed`.
- overlay: `template`, `vars`, `at`, `duration`, `track`, `sfx`, plus its opts (`cutout`, `on`, `why`, `snap`) and `block`.
- effect: `name`, `at`, `duration`.
- text: `text`, `at`, `duration`, `style` (`badge` | `word` | `cta`), plus its opts (`bg`, `font`) and `block`. Never a caption.

## Hand-back (all style agents)
- `prompts` and `edit-plan` modes: final message ≤ 20 lines: the paths (`prompts2.json` + `prompts.txt`, or `plan2.json` + `plan.json` + `plan_table.txt`), the last `check` / `check-prompts` output, decisions for the user, brief rules that could not be met (with the exact fix). No tables and no prompts in the message: the main session shows `prompts.txt` and `plan_table.txt` (and pastes every prompt in chat in full).
- `storyboard` mode: as above in that section (prompts pasted in chat, each in its own code block).
- **Re-runs for a fix:** edit the existing `plan2.json` / `prompts2.json` rows by `#` (clip number in the table, or prompt `id`), re-run the tools, and report only the changed `#`s with one line on what changed in each.
