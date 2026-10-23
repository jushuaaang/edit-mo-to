# edit-mo-to speed revamp: design

Date: 2026-10-23. Status: written from the brainstorm; the editor said "plan everything out", so the approach
below is the recommended one, with every call of mine marked **(my call)**. Findings and measurements are in
`docs/edit-mo-to-speed-revamp.md` (the handoff page); this document decides what gets built.

## Intent

`/edit-mo-to` is the editor's 12-step client-video workflow (brief → script → VO → prompts → CapCut build → review →
captions → music → export → learning). It works, but the editor waits on agents at almost every step, and on the
Windows PC it is much slower than on the Mac. The agents are slow because they **type huge files** (prompts with
lock lines repeated 50+ times, a 124k-character plan JSON), make **hundreds of small tool calls** (one per clip,
one per frame, one per SFX cue), go round **serial fix loops for mechanical mistakes** a script could catch, and
**re-read the same rules** on every dispatch. The learning step proposes rules the editor already has.

The revamp keeps the workflow and every ⛔ gate exactly as they are and changes **what agents type, how many calls
they make, and what a script does instead of a model**. Motion graphics keep the same templates and the same pixels.

## Goals

1. A full video takes materially less waiting: target **≥ 60% less agent wall time** on a Wondermint-size job
   (3 × 20 s B-roll) and on a Nativia-size job (5 × 90 s UGC), measured the same way as the baseline (file mtimes
   of the reports and the build).
2. **Fewer tokens**: agent output per job down by at least 3× (no repeated lock lines, no verbose plan JSON, no
   double emission); image tokens for checks down by 10× (tiled sheets).
3. **Light on the machine**: overlay renders 3× faster with pixel-identical output; smaller overlay files for CapCut
   playback; no internet needed to render; speech timing uses the fastest backend each machine has.
4. **Parallel where order doesn't matter**: style agents per timeline, overlay renders, QA sheets per timeline.
5. **No fix rounds for mechanical errors**: a plan that fails frame arithmetic, VO edges, reuse, overlay placement,
   generator limits or the scale convention never reaches QA or the editor.
6. **Learning step never re-proposes a known or declined rule.**
7. **Windows runs the same workflow at Mac-like speed** after the machine-specific fixes in `machine.json`.

## Non-goals

- Changing the 12 steps, the gate questions, who does captions/export, or the chat-table/`seconds:frames`/full-path
  conventions. Every prompt is still pasted in chat in full, each in its own code block.
- New motion looks or templates. New alpha formats (VP9/HEVC alpha were measured and rejected).
- Replacing VectCutAPI or CapCut 9.6. Replacing Whisper with a paid API.
- Touching `PYNK_AI_UGC_Studio`.

## Anti-goals

- Any visible change to a rendered overlay (the slim ProRes pass must stay below one 8-bit step of error).
- An agent "optimising" a lock line away: the full lock text still appears in every pasted prompt.
- Skipping a gate or a QA judgement because a script passed.
- Losing the editor's hand edits (every write still diffs the live timeline first and backs up).

## Constraints

- Python 3.12 venv in `.claude/edit-mo-to/tools/.venv`, tests with `pytest` in `tools/tests` (130 collected, 4 slow).
  New code follows the existing tool style: one file per responsibility, a CLI that prints JSON, tests beside it.
- HyperFrames pinned at 0.8.162 (upgrade to 0.8.186 is optional and separate). Templates are untouched.
- VectCutAPI endpoints: `create_draft`, `add_video` (masks, transitions, speed, transform, scale), `add_audio`,
  `add_text`, `add_video_keyframe` (`property_types`/`times`/`values` lists), `add_effect` (`params` must be `[]`),
  `save_draft` (`auto_deploy: false`). Known bug: with exactly one video track the second `add_video` fails; add
  the overlay track first.
- Mac and Windows share the repo; per-machine values live only in `.claude/edit-mo-to/machine.json`.
- Nothing personal is committed (`my-preferences.md`, `clients/`, `edit-patterns.jsonl`, `_practice/`).
- Claude Code subagent frontmatter supports `model`, `effort`, `maxTurns`, `tools`, `omitClaudeMd`.

## Approaches considered

1. **Thin the agents, keep the shape** (chosen): agents write compact specs and read a per-job context pack; new
   scripts expand, check, build and QC; the skill dispatches in parallel. Keeps every file and gate the editor
   knows; biggest gain per change; every piece testable on its own.
2. **One big orchestrator script** that runs the whole job from brief to CapCut with the model only writing the
   creative text: fastest in theory, but it would replace the skill's gates with code paths, which the editor
   explicitly does not want, and it would be hard to run on two machines with different tools.
3. **Only mechanical speedups** (render concurrency, ASR backend, Defender exclusions): safe, but it leaves the
   typing and tool-call drivers untouched, which were ~70% of the measured wait.

## Design

### 1. Compact plan (`plan2`) and expander: `tools/plan_tools.py`

The style agent writes a **frame-based plan** instead of the contract's float JSON. **(my call)** Format:

```json
{"project": "Nativia", "fps": 30, "width": 1080, "height": 1920,
 "base": "/abs/video folder/",
 "brand": {"font": "Inter", "bg": "#0e2f5a", "fg": "#ffffff", "accent": "#8fd3ff"},
 "vo": {"file": "voiceover/BODY.mp3", "volume": 1.0}, "music": null,
 "blocks": {"BODY": {"clips": [...], "overlays": [...], "effects": [...]}},
 "timelines": [
   {"name": "Timeline 01 – H1 + Body + CTA", "vo_in_f": 0, "vo_out_f": 2577,
    "seq": [{"clips": [...], "overlays": [...]}, {"use": "BODY", "at_f": 213}],
    "manual": ["check lip-sync in review"]}
 ]}
```

- A clip row is `[file, src_in_f, at_f, len_f]` or `[file, src_in_f, at_f, len_f, opts]` with `opts` only for
  non-defaults: `track` (`main` | `top` | `bottom` | `overlay`), `scale`, `x`, `y`, `speed`, `mute` (default true),
  `transition` + `transition_f`, `line`, `layout` (`split-top` | `split-bottom` | `grid`),
  `kf` = `[[t_f, scale, x, y], ...]` (keyframes), `volume`, `gain_db`.
- An overlay row is `[template, at_f, len_f, vars, track, sfx]` (`track` ∈ `ui` | `title` | `flash` | `cutout`;
  `sfx` ∈ `default` | `none` | list). Brand vars (`font`, colours) are filled from `brand` when absent.
- An effect row is `[name, at_f, len_f]`. Files are relative to `base` (absolute allowed). Times are **whole frames**.
- `blocks` are written once and reused by `{"use": NAME, "at_f": N}` in a timeline's `seq` (every row shifted by
  `at_f`). The Nativia body is thus written once, not five times.

`plan_tools.py expand plan2.json --out plan.json` writes the **existing contract plan** (seconds with 10 decimals,
`timelines[].clips/overlays/effects/texts/manual`, `vo_in`/`vo_out`), so the build and QA code keep one input format.
Expansion is deterministic; the full plan is a build artefact, never typed by a model again.

### 2. Plan check (lint) before any QA or build: `plan_tools.py check`

Runs on the expanded plan and fails fast with numbered, specific errors. Checks: every time is a whole frame;
main track has no gaps or overlaps; `src_in`/`src_out` inside the file (ffprobe, cached in `{tmp}/probe/`);
no clip reused within a timeline and no overlapping source span across the job's timelines (shared `blocks` are
exempt); VO `vo_in`/`vo_out` edges sit in silence (RMS below −60 dB in a 0.8 s window, the same probe qa.md
prescribes); every overlay starts on a cut (±1 frame) and overlays on one track don't overlap; every template
exists and its vars pass `motion_render.fill`; SFX files exist; **scale convention**: with the source's size and the
canvas, `scale` must keep the frame covered (no black edges) and not exceed 2.0 unless `opts.allow_scale`; timeline
length within `limits.min_s`/`max_s` when given; bottom 400 px caption band free of overlays (by template `y`/`top`
var when present) except `cta`/`end-card`; no `texts` captions. Style agents run `check` themselves before handing
back; the skill refuses to dispatch QA or the editor on a plan with errors.

### 3. Compact prompts (`prompts2`) and expander: `plan_tools.py prompts`

The agent writes the **lock texts once per job** (they follow the brief and the client, so they stay the agent's
words) and per-prompt only what is unique:

```json
{"generator": "google-flow", "product": "Nativia", "aspect": "9:16",
 "attach": {"@Image1": "refs/R1_headshot.png", "@Image2": "refs/product.png"},
 "locks": {"realism": "...", "product": "...", "notext": "...", "voice": "...", "look": "...", "pacing": "...",
           "style_bible": "..."},
 "prompts": [{"id": "AI-3", "line": 3, "vo_in_f": 72, "vo_out_f": 180, "gen_len_s": 4,
              "mode": "ingredients", "setting": "...", "subject": "...", "action": "0.0–2.5s: ...", "camera": "...",
              "dialogue": "...", "attach": ["@Image1", "@Image2"], "locks": ["realism", "product", "notext", "pacing"],
              "lock_overrides": {"product": "..."}, "negative": "...", "use": "0:00-2:22", "optional": false}]}
```

`plan_tools.py prompts prompts2.json --script script.txt --timings vo.json --out prompts.txt` writes the **same
deliverable as today**: the table `# | Script line | VO in | VO out | Length | Source | Prompt / Cut | Attach` and one
fenced code block per prompt with the locks in full, in the fixed order Subject · Setting · Action · Camera · Look ·
Dialogue · Locks · Attach · Negative. `plan_tools.py check-prompts prompts2.json --script --timings` fails on:
length ≠ VO span (±2 frames) unless `gen_len_s` ≥ span with a `use`; missing required locks for the style
(`required_locks` per style in `plan_tools.py`: ugc = realism, product, notext, voice, look, pacing; pixar/claymation
add style_bible; product-ad = product, notext); dialogue not a verbatim substring of the script line;
Flow: `attach` > 7 or `gen_len_s` outside 4–8; Seedance: `gen_len_s` < 4; attach keys not in `attach`; two prompts
for one line without a cut point between words.

The main session pastes `prompts.txt` into chat, as the preferences require, **once**.

### 4. Faster, lighter, offline overlay rendering: `tools/motion_render.py`

- `render(name, out, variables, fps=30, workers=1, slim=True)`: passes `--workers N` (default 1, which skips the
  1.7 s calibration launch; measured 5.0 s vs 7.3 s for a 3 s badge, PSNR 83 dB, i.e. identical).
- `render_many(jobs, concurrency=None)`: a process pool of `render` calls; `concurrency` from
  `machine.json["render_concurrency"]`, default `min(4, cpu_count // 2)`. Jobs with the same `(template, vars,
  duration)` render once and are copied (Nativia: 13 unique of 47).
- `slim(mov)`: `ffmpeg -c:v prores_ks -profile:v 4444 -vendor apl0 -pix_fmt yuva444p10le -qscale:v 6 -alpha_bits 8`
  into a temp file, then replace; measured −38 to −48% size at 58–65 dB (≤ 0.3 of one 8-bit step). On by default,
  off with `slim=False` / `--no-slim`.
- Offline: `motion/skeleton/gsap.min.js` (3.14.2, vendored once) and `fill()` rewrites the jsdelivr `<script src>` to
  the local file; Google-Fonts `<link>`s stay (HyperFrames caches them; a warm cache renders offline).
  **(my call)** Bounding-box canvases are deferred (they need per-template sizes and a clip offset); they are listed
  under "Later".

### 5. Tiled frame sheets for every visual check: `tools/sheets.py`

`sheets.py clips plan.json "<timeline>" out_dir` grabs the middle frame of every placed clip (or in/mid/out for
AI clips with `--ai`) at 270×480, tiles 4×3 per sheet with the clip number drawn in the corner (Pillow; this
ffmpeg's `drawtext` crashes), and prints the sheet paths with a `sheet → clip numbers` index. `sheets.py overlays`
composites each overlay's middle frame on the A-roll frame under it (the qa.md "face and mouth clear" check) and
tiles those. One sheet ≈ 2,000 image tokens for 12 clips, versus ≈ 300 × 12 as single reads and 12 calls.
The build writes the sheets; QA reads the same files instead of re-rendering.

### 6. One-shot build: `tools/build_project.py` (generalised from `plan_build.py`)

`build_project.py build plan.json [--import f ...] [--timelines "A,B"] [--job NAME]` does, in one process:
render + slim overlays in parallel (deduped), cutouts, per timeline: `create_draft`, overlay track first (API bug),
every clip (`add_video` with masks for `split-top`/`split-bottom`, `transition`, `speed`, transform/scale, volume),
keyframes (`add_video_keyframe` with `property_types` `uniform_scale`/`position_x`/`position_y`, `times` in timeline
seconds, first point +1 ms), effects (`add_effect`, `params: []`), VO span ending on a whole frame, music,
`sfx_cues`, `save_draft`, `wait`; then `compose`, `import` (plan sources + `--import` files), `edit_diff snapshot`
per timeline, `sheets.py clips` per timeline, and a report: `{tmp}/reports/<job>/build_report.txt` (the placed-clips
table) plus a ≤ 25-line JSON summary on stdout (project path, timeline ids, counts, sheet paths, failures, manual
list). The media-panel edit the editor used to do by hand is dropped: `import` already lists the files (the
hand edit produced 65 bad entries on Nativia). Also `build_project.py timeline plan.json "<name>"` (one draft,
for `revise-new-timeline` / `revise-in-place`) and `build_project.py music plan.json "<name>" --music f --volume v`.
`plan_build.py` stays for the frame-plan quick route and `/practice-muna`; its `sfx_cues`/`beat_snap`/`check_plan`
move into a shared module both import.

### 7. Mechanical QA by script: `tools/qa_check.py`

`qa_check.py build plan.json "<project>" [--timelines ...] [--changed 3,7,ov2] [--brief limits.json]` runs the
qa.md build-gate checks that need no eyes: every planned clip present at its time (±2 frames) and length, no
extras, tracks and volumes as planned, VO span per timeline with RMS-silent edges, rotation vs stored size,
split masks and grid scales, overlays on cuts, no reuse across timelines, dead visual stretches > 2.2 s (advisory)
and talking head > 5 s without B-roll, SFX ≤ 3 consecutive same file, music ≈ −20 dB (ebur128 only when volumes
look off), duration within `limits`, canvas ratio, no caption/subtitle tracks. Output: only FAIL and OPEN rows
(`# | Check | Status | Evidence | Fix`) plus `passed: N`; `--changed` restricts to those items and their
neighbours (true delta). `qa_check.py prompts` wraps `plan_tools.py check-prompts`. The QA **agent** then does only
the pixel and meaning judgements from the sheets: clip fits its line, AI slop, baked-in text, face/mouth/label
clear, and the brief-checklist rows that need reading.

### 8. Context packs and compact timings

- `tools/context_pack.py <style> [--client name] [--generator g] --out pack.md`: General + the style's section +
  the generator's section + "Known generation failures" from `preferences.md`, then the same sections from
  `my-preferences.md` (marked "editor's own rules, win on conflict"), then the client file. One Read per agent run
  instead of 3–4, and ~40% of the characters. Written once per job by the skill; reused unchanged across re-runs.
- `media_timing.py vo <audio> [script] --compact`: `lines` as `n|start_sf|end_sf|matched|text` and `words` as
  `word|start_f|end_f` lines (9× smaller than the indented JSON). Agents get the compact form; the JSON stays for
  tools.
- Style agents keep `model: inherit`; `editor` becomes a thin runner on `model: sonnet`, `maxTurns: 40`; `qa` stays
  `model: sonnet`. **(my call)** Subagent cache TTL 1 h via `CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL=1h` in the
  skill's notes (environment, not a file this repo controls).

### 9. Speech-timing backend per machine: `media_timing.py`

`transcribe()` picks a backend from `machine.json["asr"]`: `"faster-whisper"` (default; now with
`BatchedInferencePipeline`, `batch_size=8`, `device="cuda"` when `ctranslate2.get_cuda_device_count() > 0`) or
`"mlx"` (`mlx-whisper`, model `mlx-community/whisper-large-v3-turbo`, Mac only). Output shape unchanged, cache
unchanged. Word-timing accuracy is unchanged (same Whisper family); the alignment code is not touched.

### 10. Learning step that knows what it already knows: `tools/learn.py`

- Every write by `capcut_project.py` (`replace`, `patch`, `add-overlay`, `add-tracks`, `add-timeline`) saves
  `<project>/edit-mo-to-backups/<timeline>.last.json` (the `segments()` dump after the write). `edit_diff.py diff
  --last "<project>" "<timeline>"` compares that with the live timeline, so agent patches are no longer counted as
  hand edits.
- `learn.py propose --patterns <diff.json> --notes <notes.txt> --out proposals.json`: turns recurring patterns and
  the session's quoted corrections into candidate rules, then **drops any candidate that matches an existing line**
  in `preferences.md`, `my-preferences.md` or `learning-declined.jsonl` (token-set similarity ≥ 0.6 after
  normalising numbers and client tags). `learn.py decline "<rule>"` appends to `learning-declined.jsonl` (local,
  gitignored). `learn.py save "<rule>" --section "B-roll" [--client name]` appends to `my-preferences.md` or the
  client file. The learning reference tells the skill to show only `proposals.json` rows.

### 11. Orchestration (skill and agent text)

- Style agents read the context pack, write `plan2.json`/`prompts2.json`, run `expand` + `check` (or `prompts` +
  `check-prompts`) themselves, fix until clean, and hand back paths plus ≤ 20 lines. They no longer write a plan
  table (the expander writes `plan_table.txt`) or paste prompts (the main session pastes `prompts.txt`).
- Dispatches that don't depend on each other go out in one message: one style agent per timeline/ad, QA per
  timeline, cataloguing shared via one `inventory.json` per job (clip inventory + contact sheets written once by
  `sheets.py inventory <folder>`; fix rounds reuse it).
- Step 6: `check-prompts` first; QA agent only for meaning and brief rows. Step 7: `check` → `build_project.py`
  → `qa_check.py` → QA agent on sheets (delta after fixes). Step 9: the hand-edit diff (`--last`) always runs before
  a patch; small timing/swap changes become `patch` ops written by the editor runner, not a re-plan.
- Gates: a gate already answered in the brief message or earlier is confirmed in the job card, never re-asked;
  "quit CapCut" is asked once per review round, not per write. The ⛔ list itself is unchanged.
- Learning: `learn.py propose` output only; declined rules recorded.

### 12. Windows

Machine-specific, through `machine.json` keys `asr`, `render_concurrency`, `render_workers` and the README's
Windows section: Defender exclusions for `{tmp}` and the tools venv (the editor adds them; the doc gives the
PowerShell), the CUDA check, and the measured numbers from the Windows session written into the handoff page.
If the Windows analysis finds a cause not covered here, it becomes a follow-up task, not a silent change.

## Decisions from the builder check (all my calls unless marked)

1. **Compact specs expanded by a tool** is the foundation; the editor has not confirmed it in so many words.
   Tasks 1–4 of the plan build exactly that piece first, and the hand-over asks for the editor's yes before the
   rest is implemented. **(editor's call, pending)**
2. **The contract plan grows** rather than the expander dropping fields: clips may carry `keyframes`,
   `transition_duration`, `gain_db`, `allow_scale`, `block`, `shared`, `line`, `layout`; each timeline may carry
   `effects: [{"name", "at", "duration"}]`. `build_project` and `qa_check` consume them; `edit_diff` ignores
   unknown keys. The contract document lists them.
3. **Scale convention:** CapCut fits a source into the 1080×1920 canvas (uniform scale to fit, upright size used
   for ±90° rotated sources) and `scale` multiplies that fit, so `scale 1.0` fills the frame for any 9:16 source
   (576×1024 included). The check computes `fitted = fit(upright_size, canvas)` and reports "black edges" when
   `scale × fitted < canvas` on either axis, and "above 2.0" when `scale > 2.0` without `allow_scale`.
4. **Overlays off a cut** are an error unless the overlay row's optional 7th element `opts` sets
   `"on": "word"` or `"on": "beat"` (the preferences allow starts on a spoken word; beat-snapped overlays are by
   design). `qa_check` reports off-cut overlays as OPEN, not FAIL.
5. **Cross-timeline reuse** is checked for every row except `block` rows and rows with `opts.shared: true`
   (host A-roll files that hook timelines legitimately share). Within one timeline the check always applies.
6. **Storyboard mode uses prompts2 too:** each prompt has `kind: "video" | "keyframe" | "character"`;
   image kinds render the `# | Script line | Shot | Save as` table and skip the VO-length and dialogue rules.
7. **Revisions get a generator:** `plan_tools.py ops old_plan.json new_plan2.json "<timeline>" --segments dump.json
   --out ops.json` diffs the old and new plan rows for that timeline, maps old rows to live CapCut segment ids
   through the `segments` dump (match on `source` + `src_in` ±1 frame), and emits `capcut_project.py patch` ops
   (`set` for changed `at`/length/`scale`/`x`/`y`/`speed`/`volume`, `remove`, `insert` with the new clip's fields);
   rows it cannot map are listed, never guessed. The editor runner applies it with `--dry-run` first.
8. **`limits.json`** is written by the main session at step 2 from the brief checklist, at
   `{tmp}/reports/<job>/limits.json`: `{"min_s", "max_s", "ratio": "9:16", "fps": 30, "caption_band_px": 400,
   "no_text": false}`; keys absent when the brief says nothing. Every dispatch passes its path.
9. **The ≥ 60% wall-time target is the acceptance test**, run as the last plan task on a real job size; tests
   passing means "built", the measured pilot means "done".
10. **Windows is a gated phase on the PC** (plan Task 15); it does not block Tasks 1–14, and goal 7 is met when its
    numbers are in the handoff page.
11. **Dropping the media-panel hand edit is confirmed by test:** the build integration test asserts
    `draft_meta_info.json` lists every plan source once, with an absolute path, after `compose` + `import`.
12. **Product ads:** `check-prompts` with `style: product-ad` takes no script or timings; required locks are
    `product` and `notext`; lengths are checked against the generator's limits only; `--beats` is accepted and
    ignored for now (beat-snapping already lives in `plan_build.py --snap-beats`).

## What stays for later

- Bounding-box overlay canvases with clip offsets (needs per-template sizes; −65% decode CPU).
- HyperFrames 0.8.186 upgrade (font stall fix, Google-Fonts CSS cache).
- Forced alignment from the script (ElevenLabs timestamps or MFA) when the editor has an API key or wants the
  install.
- A cheaper cutout backend (rembg session reuse, Apple Vision, RVM).

## Left to the builder

- Internal module layout of `plan_tools.py` (one file or a package) as long as the CLI and function names in the
  plan hold.
- Exact wording of the rewritten agent and skill sections, keeping every rule the editor has and the gate wording in
  `reference/steps.md`.
- Test media: synthetic clips via ffmpeg `testsrc2`/`sine` as the existing tests do; real-API tests skip when
  port 9001 is down.
