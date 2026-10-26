# Captions by Claude, and temporary English captions (design)

## Intent and why

Two changes the editor asked for, built on one caption tool:

1. **Temporary English captions.** When the script's language is not English or Filipino, the editor and QA cannot easily follow the meaning while reviewing (Spanish Uvola, German VSL test). Every build of such a job carries an English translation of each script line at the top of the frame, clearly temporary, which the editor deletes when all checking and reviewing is done. Claude reminds them.
2. **Step 10 becomes a choice.** Today the editor always runs CapCut auto-caption. Now step 10 asks who adds the captions, with three options:
   1. the editor runs CapCut auto-caption (today's way);
   2. Claude adds CapCut text captions (fast, script-exact words, simple animation);
   3. Claude renders animated word-by-word captions (only when the brief or reference calls for it; about 3-4 min extra render per 90 s ad on the Windows PC).

Claude's captions use the script's exact words (auto-caption misspells Spanish/German and brand names) timed to the VO's word timings, and cost a few thousand tokens per timeline because a script makes them, not the model.

## Goals

- Temporary English track on every build of a non-English, non-Filipino script, from the first build, on every timeline.
- Step 10 asks the three-way question; options 2 and 3 are done by tools, not by typing captions.
- Captions are added to the reviewed timeline without touching the editor's hand edits.
- QA checks Claude's captions mechanically (words = script, timing = VO, position).

## Non-goals

- Translating on-screen badges or overlay text (only script lines).
- Reproducing CapCut's own caption presets/animations.
- A translation API: the main session writes the translation.
- Saving any caption choice to client notes or preferences automatically.

## Anti-goals (failure even if it "works")

- The temporary English track ends up in an export.
- Captions with words different from the script, or out of sync with the VO.
- Adding captions overwrites or shifts the editor's hand edits.
- A plain English or Filipino job shows any temporary track or extra question.
- The agents type caption chunks by hand (token cost the speed revamp removed).

## Constraints

- The 12 steps stay; no new gate. Step 10's existing ⛔ gate changes its question (wording below); the gate count stays the same.
- Every write to a CapCut project goes through `capcut_project.py` (busy check, backup, last-write snapshot).
- Times in whole frames at 30 fps; word timings from `media_timing.py vo` (JSON).
- Motion templates are not edited; option 3 uses the existing `ugc-captions` template (its chunking rules: cut at punctuation and pauses first, then `max_words`; no one-word orphan; numbers stay with their unit; script is the source of truth for words).
- Caption band: bottom `caption_band_px` (400 px) stays reserved for the real captions; the English track sits at the top.

## Approaches (picked: A)

- **A. One caption tool used by both features (picked).** A new `tools/captions.py` turns script lines + VO word timings into caption chunks: for real captions, chunks per the `ugc-captions` rules; for the English track, one chunk per script line with the translated text. The English track is added at build time as text rows; real captions are added after review with `capcut_project.py add-tracks` (the route music uses), keeping hand edits. Option 3 feeds the same timings to `ugc-captions` and renders in parallel parts. Cheap per job; one tool plus small changes to build, QA and docs.
- B. The style agent writes caption rows into the plan. Rejected: ~70 chunks per 90 s ad typed in every fix round, the token cost the revamp removed.
- C. Captions only at step 10, English track added separately later. Rejected: the first build would lack the translation, which defeats its purpose.

## What was decided (behaviour)

### Temporary English captions
- **Trigger:** at step 2/3, the script language is noted on the job card. Not English and not Filipino (Tagalog/Taglish counts as Filipino) → temporary English on.
- **Translation:** at step 3, the main session writes a literal English line for each script line, shown next to the script in the script table so the editor can correct it; saved as `{tmp}/reports/<job>/script_en.txt`, one line per script line, same order and count as `script_file`.
- **Placement:** top of the frame, above everything (over badges and overlays too): its own CapCut text track named `TEMP_EN_delete_me`, placed as the top layer. Small white text on a semi-transparent dark box; clearly a review aid.
- **Timing:** each translated line spans its script line's VO span (from the word timings), per timeline (hooks and bodies use their own VO spans).
- **When:** added by the build from the first build, on every timeline, and kept on revisions (new timelines get it; in-place patches don't remove it).
- **Removal:** the editor deletes the track when all checking and reviewing is done. Reminders: on the job card from the first build ("TEMP_EN on: delete before export"), and at step 12's hand-off as the first line.
- **QA:** the build and review gates ignore this track for caption/extras checks and show one OPEN row "TEMP_EN present (delete before export)".

### Step 10 choice
- Gate wording replaces today's Captions line: "Captions: will you run CapCut auto-caption yourself, or should I add them: simple text captions (fast), or animated word-by-word (about 3–4 min render per ad)?"
- **Option 1:** today's flow unchanged (editor runs auto-caption, says when done).
- **Option 2 (CapCut text):** `captions.py` makes the chunks → a small draft with one text track `captions` → `capcut_project.py add-tracks <project> <timeline> <draft> --type text` (add-tracks gains text support if it lacks it). Style: the editor's usual caption look from `preferences.md`/`my-preferences.md` (a new "Captions" section; starter defaults: bold sans, white, black stroke/shadow, bottom band, 2-4 words per chunk) plus a simple pop/fade in per chunk where VectCutAPI's text supports it.
- **Option 3 (animated):** render `ugc-captions` (`highlight: active-word`) with `words_file` + `script_file`, split by `t_from`/`t_to` into up to `render_concurrency` parts rendered in parallel, then added as an overlay video track on the timeline via the same add-tracks route.
- **Hand edits:** before adding captions, the editor agent runs the hand-edit diff (`edit_diff.py diff --last … --log`) as before every write.
- **QA after captions:** `qa_check.py captions` (new subcommand) compares the added caption segments with the script words (exact, case-insensitive, punctuation-insensitive), checks each chunk lies within its words' VO span (±2 frames), sits in the caption band, and reports gaps > 0.5 s inside speech.
- **Rule change:** "never add captions" becomes "never add captions before step 10, except the TEMP_EN review track; at step 10 the editor chooses". Updated in `CLAUDE.md`, `preferences.md`, `SKILL.md`, `steps.md`, `editor.md`, `qa.md`, `docs/edit-mo-to-design.md`, `practice-muna` (its step 10 tip).
- **qa_check `captions` row at the build gate:** stays a FAIL for caption/subtitle text before step 10; `TEMP_EN_delete_me` is exempt.

## Calls made after the builder check (Claude's calls, for the editor to check)

1. **Word timings in other languages (in scope).** `media_timing.py vo` today uses the English-only `small.en` model and drops accented letters when matching, so Spanish/German timings fail (the Uvola job used a one-off `txw.py`). `media_timing` gains a `--lang` taken from the job card's script language: English keeps `small.en` and today's exact behaviour; any other language uses the multilingual `small` model with that language forced, and word matching keeps Unicode letters. The transcript cache key includes model and language (English keys unchanged, so existing English caches stay valid).
2. **Captions follow the timeline as it is at step 10, not the original plan.** `captions.py` maps word times through the timeline's real VO segments (from `capcut_project.py segments`), so trims, splits and moves the editor made are followed; words of a cut VO stretch are dropped. QA's "words = script" check compares against the script minus the cut stretches, and lists what was dropped.
3. **QA for option 3** checks the chunk list that went into the render (words vs script, timing vs VO), the overlay segment's start and length on the timeline, and reads one contact sheet of caption frames; no text segments are needed.
4. **TEMP_EN after the editor deletes it.** When the editor says the temporary track is removed (or the hand-edit diff sees it gone), the job card records "TEMP_EN removed" and later builds and new timelines do not add it back unless the editor asks. The deletion of `TEMP_EN_delete_me` is never logged as a learned hand edit.

## Left to the builder

- Exact chunker implementation, sharing rules with `ugc-captions` (mirror them in Python; the template stays untouched).
- Exact text sizes/positions/colours within the stated look; VectCutAPI text animation parameters if available (if none, no animation, say so).
- How the top layer is guaranteed (render index / track order) for `TEMP_EN_delete_me`.
- Whether `add-tracks` needs a `text` mode or a separate `add-text-track` command.
- Splitting option 3 renders across timelines that share a body (reuse identical parts).
