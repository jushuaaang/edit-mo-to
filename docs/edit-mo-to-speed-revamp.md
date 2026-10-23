# edit-mo-to speed revamp: summary, findings and plan

Status: **brainstorm in progress** (started 2026-10-23 on the Mac). No workflow file has been changed yet.
This page is the shared handoff between the Mac session and the Windows session. The Windows session
adds its findings under "Windows findings" below; the design doc comes after that.

## What the editor wants (their words, condensed)

- Keep the 12-step `/edit-mo-to` workflow and every ⛔ gate exactly as they are.
- Make it **faster**: less waiting on agents to think and hand back ("at almost every step").
- **Token efficient**, **lightweight on the PC and processor**, agents working **in parallel**, planning faster.
- **Same or better video quality, especially the motion graphics.** Nothing may change how the graphics look.
- Remove the bottleneck.
- The learning step must **not propose a rule that already exists** in `preferences.md` or `my-preferences.md`.
- **The main problem is on Windows: there it takes really so much time.** The Mac (Apple M4, 16 GB) is the fast one.

**Approved by the editor (2026-10-23):** agents may write **short specs that a tool expands** into the full prompts
and the full plan, as long as every full prompt still lands in chat and the CapCut project is the same.
Design: `docs/superpowers/specs/2026-10-23-edit-mo-to-speed-design.md`. Plan:
`docs/superpowers/plans/2026-10-23-edit-mo-to-speed.md` (16 tasks; execution started in its own session on the Mac).

## What was measured (Mac, 2026-10-23)

### Where the agent time went on the last two real jobs (file timestamps)

| Wondermint (3 B-roll ads × 20 s, 32 clips, 4 overlays) | min |
|---|---|
| Prompts gate, 3 serial fix rounds (13 → 7.5 → 9 min, still FAIL) | 33 |
| Edit plan | 7 |
| Build | 12 |
| Build QA | 8 |
| Revision 1 (SFX re-timed to visible events) | 16 |
| Hook rebuild after a blind patch overwrote hand edits | 19 |

About 100 minutes of agent time in a 4 h 08 min job. Nativia 2 (5 timelines × 90 s, 224 clips, 47 overlays,
~95 SFX cues): build 13 min; build QA 4.2 min; a revision whose prep took 17 min and whose apply took 46 s;
the body built five times and four copies thrown away (hook-only format decided after the build); 38 patch backups.

### The four causes, largest first

1. **Typing huge files.** Nativia's style agent wrote ~140k output tokens (storyboard 148k chars emitted twice,
   prompts 104k chars, plan JSON 124k chars + a 24k-char table of the same rows). Lock lines are ~50% of every
   prompt and 78% of the keyframe prompts, repeated verbatim by rule ("never same as above"). The plan JSON
   carries 4 copies of the body, 10-decimal floats and constant default keys (~60% of its size). The main
   session then pastes every prompt into chat again (each prompt is generated twice).
2. **Hundreds of small tool calls.** Cataloguing client clips is 3 calls per clip (ffprobe, contact strip,
   Read), redone in every fix round (up to ~170 calls per 3-ad job). The editor, as written, makes one JSON
   body + one curl per clip (220 clips → 440 calls), 4–6 calls per overlay, one `add_audio` per SFX cue
   (~196 calls), then one ffmpeg frame + one Read per placed clip; QA grabs the same frames again two minutes
   later. QA's mechanical checks run one model turn at a time (~22 turns of a 4-minute run).
3. **Serial fix loops for mechanical mistakes.** Half of Nativia's prompt-gate FAILs were timing arithmetic
   (cuts off word onsets, VO tails mid-sound). One scale-convention mix-up (1.875 vs 1.0 fills) on Wondermint
   cost ~37 min and four agent runs. Delta QA runs cost as much as full runs. Each gate is a serial chain
   agent → QA → fix → delta QA → main session → editor.
4. **Cold starts and re-reads.** Every dispatch re-reads 23k–36k chars of rules (contract, preferences,
   client file, catalogue); VO word timings are passed as verbose JSON (Nativia 54k chars; a compact
   `word,start,end` form is 9× smaller). QA (Sonnet) spends ~80% of its output on thinking.

Also: the learning step reads the agents' own later patches as the editor's hand edits (edit-patterns.jsonl
is mostly agent patches), never re-reads the existing rule files before proposing, and records nothing about
rules the editor declined. That is why it re-proposes known rules.

### Motion graphics (measured on the Mac with the real `badge` template; HyperFrames 0.8.162)

- Baseline 6.9–7.5 s per 3 s overlay: 1.7 s is a worker-calibration browser launch, 2.8 s capture, 1.3 s encode.
- `--workers 1` removes the calibration: 5.0 s, pixels identical within measurement (83 dB PSNR).
  Rendering 3–6 overlays side by side (separate processes): ~2.3 s per overlay. 45 overlays: 5.2 min → ~1.8 min.
  `--batch` gives the same gain but needs template changes; it does not keep a warm Chrome.
- After (Windows PC, 3 s `badge`, `motion_render.py render`, two runs each): old behaviour (no `--workers`, no slim) 22.7 s / 23.6 s, 10.5 MB; new default (`--workers 1` + slim) 16.7 s / 16.3 s, 6.8 MB (-36%). HyperFrames logs `drawelement` capture here (not `screenshot`; 5 clip-boundary frames fall back to screenshots), with capture ~11 s dominating. Slim PSNR vs unslimmed: 73 dB.
- Nativia rendered 47 overlays where only 13 were unique (same template + vars): dedupe before rendering.
- ProRes 4444 re-encode (`prores_ks -profile:v 4444 -qscale:v 6 -alpha_bits 8`): files −38% to −48%
  (16.8 → 10.4 MB, 14.3 → 7.4 MB), error 0.1–0.3 of one 8-bit step, 0.4 s per file. Lighter for CapCut playback.
- Bounding-box canvas (render the badge at 1080×420 instead of 1080×1920, offset the clip in CapCut):
  decode CPU −65%, files −13% more. Needs a per-template canvas size and a position offset in `capcut_project.py`.
- VP9/HEVC alpha formats were tested and **rejected**: visibly worse (21.8 dB min) and CapCut support unconfirmed.
- Fonts and GSAP can be local (fonts cached in `~/.cache/hyperframes/fonts`, GSAP copied into `skeleton/`):
  pixel-identical, no internet needed. HyperFrames' **fast frame capture is macOS-only**; Windows uses the slow
  screenshot path (one suspect for the Windows slowness).
- Cutout (u2net_human_seg) at ~1.3 s/frame is probably per-frame session overhead: rembg u2net measures
  0.12 s/frame on CPU; Apple Vision person segmentation ~60 fps on M-series; RVM 100+ fps on an NVIDIA GPU.

### Speech timing and QC (web research)

- With the script known, word timings do not need Whisper: ElevenLabs `with-timestamps` returns them with the
  VO it generates; a forced aligner (ElevenLabs Forced Alignment API, or local MFA) aligns an existing VO to the
  script at ~20–40 ms error. Whisper word starts run ~150 ms early on average. If ASR stays: parakeet-mlx or
  mlx-whisper on the Mac (0.5–1.0 s vs 7 s for faster-whisper CPU on a short clip); on Windows faster-whisper
  with `batch_size=8` (3.7× on an RTX 3070 Ti, ~2× on CPU) or Parakeet via onnx-asr.
- Image tokens are `ceil(w/28) × ceil(h/28)`: a 1080×1920 frame ≈ 2,700 tokens; a 4×3 sheet of 270×480 tiles
  ≈ 2,000 tokens for 12 frames. 220 clips: ~19 sheets ≈ 38k tokens instead of ~590k, 19 reads instead of 220.
- Mechanical QC without a model: reuse from (file, in, out) ranges in the plan; baked-in text via PP-OCR
  detection (~19 ms/frame); faces via YuNet (<1 ms); scene cuts via ffmpeg/PySceneDetect; CLIP-style similarity
  to flag clips that don't match their line, so a model looks only at the flagged ones.
- Claude Code subagents: `model: haiku` + `effort: low` for mechanical agents, `omitClaudeMd: true`, `maxTurns`,
  results to a file plus a short return; subagent prompt cache TTL can be raised to 1 h
  (`CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL=1h`).
- VectCutAPI has no batch endpoint; the per-clip cost is the model's tool calls, not HTTP. One Python process
  can build a whole timeline from the plan. (pyJianYingDraft targets JianYing, not CapCut; VectCutAPI stays.)

## The plan (draft; the editor picks the approach and approves a design doc before anything is built)

The workflow, its 12 steps and gates stay. What changes is **how much the agents type, how many calls they make,
and what a script does instead of a model.**

1. **Compact specs + expander/linter** (`tools/plan_tools.py` or similar). Style agents write per-shot specs and a
   frame-based plan; the tool expands lock blocks and style bibles from `preferences.md`, `my-preferences.md`,
   `style-blocks.md` and the client file into the full prompts file (pasted in chat in full, as now) and the
   full plan JSON (same schema the editor builds from). The tool rejects a bad plan before QA: frame
   arithmetic, VO edges by audio level, reused clips, scale convention, overlays on cuts, lengths.
   Expected: 3–5× less agent output, no more timing-arithmetic fix rounds, prompts typed once.
2. **One-shot build.** Extend `plan_build.py` to the contract's plan shape so one command builds a timeline:
   dedupe + render overlays in parallel (`--workers 1`, 3–6 at once), lighter ProRes, SFX cues, every clip
   with masks/keyframes/transitions/effects, VO span, save, wait, compose, import, media panel, snapshot, and a
   tiled self-check sheet per timeline. The editor agent becomes a thin runner (or the main session runs it).
   Expected: ~1,400 calls → a handful; build minutes instead of tens of minutes.
3. **QA split.** `qa_check.py` does every mechanical check in seconds and emits only FAILs; the QA agent
   (Haiku/Sonnet, low effort) judges pixels from tiled contact sheets reused from the build, only for flagged or
   sampled clips. Delta mode checks only the changed items. Expected: build QA ~8 min → ~1–2 min; far fewer tokens.
4. **Context packs.** One slim rule pack per job and style (only the sections that apply, one lock block,
   compact word timings), reused unchanged across fix rounds; agents on the cheapest model that does the job;
   `omitClaudeMd` for self-contained agents; longer subagent cache TTL.
5. **Orchestration.** Dispatch independent agents in one message (per timeline, per ad); never re-ask an answered
   gate; run the plan check before the build; always diff hand edits before a patch (already a saved rule);
   revisions as ops the tool applies, not re-plans.
6. **Speech timing from the script** (ElevenLabs timestamps or forced alignment), with the machine-specific
   fast ASR as fallback (Mac: MLX; Windows: batched faster-whisper, CUDA if a GPU exists).
7. **Learning step.** Snapshot after every agent patch so hand edits are separated from agent edits; before
   proposing, read `preferences.md` + `my-preferences.md` and drop anything already covered; keep a small
   `learning-declined.jsonl` so a declined rule is not offered again.
8. **Motion graphics quality kept.** Same templates, same pixels; only render concurrency, file size, canvas size
   and offline fonts change. Any new look still goes through `motion-designer` and its `check` gate.
9. **Windows.** Whatever the Windows findings below say (Defender scanning the build area, slow capture path,
   CPU-only Whisper, disk, Node/Python versions). Fixes are machine-specific and go through `machine.json`.

## For the Windows session: what to analyse there

Read this page, `CLAUDE.md`, `docs/edit-mo-to-design.md`, `.claude/skills/edit-mo-to/SKILL.md`,
`.claude/agents/editor.md`, `.claude/agents/qa.md`, `.claude/edit-mo-to/style-agent-contract.md`,
`.claude/edit-mo-to/tools/motion_render.py` and `plan_build.py`. Then measure on the PC (keep each test short,
write results under "Windows findings" below with the numbers):

1. **Hardware:** CPU model, RAM, GPU (NVIDIA? CUDA available to Python?), and whether `D:\Video Editing`, `{tmp}`
   and the CapCut drafts folder are on an SSD or a hard disk (`Get-PhysicalDisk | select MediaType`).
2. **Overlay render:** time `motion_render.py render badge <out.mov> --vars-file <json>` (3 s badge) once as is,
   once with `HYPERFRAMES` `--workers 1` (edit the call or run `hyperframes render` directly), and note whether
   HyperFrames reports screenshot or fast capture. Note Node version and whether Chrome launches with GPU.
3. **Speech:** time `media_timing.py vo <a VO file>` cold and with the cache (`--no-cache` for cold); check whether
   `faster-whisper` can use CUDA (`ctranslate2.get_cuda_device_count()`), else CPU thread count.
4. **Build backend:** VectCutAPI health (`curl http://localhost:9001/`), time of one `add_video` call, time of
   `capcut_project.py compose` on a small draft, and whether the build area `{tmp}/build` is excluded from
   Windows Defender (`Get-MpPreference | select ExclusionPath`). Try one timed build with and without a temporary
   exclusion if allowed.
5. **Disk churn:** size of `{tmp}/build`, `{tmp}/qa`, and VectCutAPI's copied assets after one build.
6. **Agent waits:** from the Windows session transcripts (`%USERPROFILE%\.claude\projects\...`), the wall time of
   the last editor, QA and style-agent runs on Windows, to compare with the Mac numbers above.
7. **Anything else that is slower only on Windows** (path length, `shell=True` subprocess cost, pythonw backend,
   antivirus, PowerShell vs bash in Claude Code).

## Windows findings

(The Windows session writes here.)

## Next steps

1. Editor answers the open question (short specs expanded by a tool: yes or no).
2. Windows session fills in "Windows findings".
3. The Mac or Windows session lays out 2–3 approaches, the editor picks one.
4. Design doc at `docs/superpowers/specs/2026-10-XX-edit-mo-to-speed-design.md`, reviewed, approved.
5. Implementation plan (`superpowers:writing-plans`), then the build, behind the test suite in `tools/tests/`.
