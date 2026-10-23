# edit-mo-to Speed Revamp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/edit-mo-to` finish a video with far less waiting by having agents write compact specs that scripts expand, check, build and QC, while the 12 steps, the gates and the motion-graphics pixels stay exactly as they are.

**Architecture:** New Python tools under `.claude/edit-mo-to/tools/` (`plan_tools.py`, `build_project.py`, `qa_check.py`, `sheets.py`, `context_pack.py`, `learn.py`, `plan_common.py`) take over everything deterministic; `motion_render.py` renders overlays in parallel, slimmed and offline; the agent and skill markdown is rewritten to use them. The contract plan JSON stays the one format the build and QA consume; the compact `plan2`/`prompts2` formats are what agents write.

**Tech Stack:** Python 3.12 (venv `.claude/edit-mo-to/tools/.venv`), pytest, ffmpeg/ffprobe, Pillow (new), HyperFrames 0.8.162 (pinned), VectCutAPI on `http://localhost:9001`, faster-whisper / mlx-whisper, Claude Code skills and subagents.

**Spec:** `docs/superpowers/specs/2026-10-23-edit-mo-to-speed-design.md` (findings: `docs/edit-mo-to-speed-revamp.md`)

## Global Constraints

- The 12 steps, every ⛔ gate and its wording in `reference/steps.md`, "deliverables in chat as tables", `seconds:frames`, full paths, 9:16 default, "never add captions", "the user exports" are unchanged.
- Every prompt is still pasted in chat in full, each in its own code block, with the lock lines in full.
- Motion templates in `motion/templates/` are not edited. Rendered pixels must stay within 0.3 of one 8-bit step (PSNR ≥ 58 dB) of the current output.
- Python tools: one responsibility per file, CLI prints JSON, tests in `tools/tests/`, run with `"{python}" -m pytest tests -q`. Real-API tests skip when port 9001 is down; real renders are marked `slow`.
- Times inside tools are whole frames at 30 fps or integer microseconds (`US(frame) = round(frame * 1e6 / 30)`); the contract plan writes seconds with 10 decimals.
- Per-machine values only in `.claude/edit-mo-to/machine.json` (new keys: `asr`, `render_concurrency`, `render_workers`); defaults in `tools/machine.py`.
- Never commit or push `my-preferences.md`, `clients/`, `edit-patterns.jsonl`, `learning-declined.jsonl`, `_practice/`, `machine.json`. Never push at all; the editor pushes.
- VectCutAPI: add the overlay track before the second `add_video` on a draft with one video track; `add_effect` `params` must be `[]`; `save_draft` with `auto_deploy: false`; always `wait` for the draft folder.
- Every write to a CapCut project goes through `capcut_project.py` (busy check, backup); nothing hand-edits `draft_content.json`.

## Review Focus

- A `plan2` timeline that uses the same block twice, or two clips from one file with overlapping source spans: `check` must report reuse (test in Task 3).
- A `vo_out_f` past the end of the VO file, or a VO edge in speech: `check` reports it instead of crashing on the probe (test in Task 3).
- An overlay var that is a media file path (`phone-cards` `video1`): dedupe keys and the copy of a deduped render must still include it, and the file must be staged per render (test in Task 5).
- `slim()` on a path with spaces and on Windows: the temp file sits next to the output and the replace is atomic; a failed ffmpeg leaves the original untouched (test in Task 5).
- `qa_check` on a `segments()` dump whose `source` is still a `##_draftpath_placeholder_…##` path: a FAIL row "unknown source", never an exception (test in Task 8).
- A Flow prompt whose VO span is 2.4 s: `check-prompts` accepts `gen_len_s: 4` with a `use` span and rejects it without one (test in Task 4).

---

### Task 1: Shared plan helpers (`plan_common.py`)

**Files:**
- Create: `.claude/edit-mo-to/tools/plan_common.py`
- Modify: `.claude/edit-mo-to/tools/plan_build.py:1-200` (move `US`, `SFX_TRACKS`, `MERGE_US`, `sfx_cues`, `beat_snap`, `check_plan` out; import them back)
- Test: `.claude/edit-mo-to/tools/tests/test_plan_common.py`

**Interfaces:**
- Produces: `US(frame: int) -> int`; `sfx_cues(overlays: list[dict], end_us: int | None = None) -> list[dict]` (overlay = `{"template", "from", "to", "vars", "sfx"}` in frames; cue = `{"file", "at_us", "len_us", "volume", "track"}`); `beat_snap(...)`; `check_plan(plan: dict) -> list[str]`; `SFX_TRACKS`.
- `plan_build` re-exports all of them unchanged (`from plan_common import US, SFX_TRACKS, MERGE_US, sfx_cues, beat_snap, check_plan`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_plan_common.py
import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import plan_common as pc
import plan_build as pb

def test_plan_build_reexports_shared_helpers():
    assert pb.sfx_cues is pc.sfx_cues and pb.US is pc.US and pb.check_plan is pc.check_plan

def test_us_is_integer_microseconds():
    assert pc.US(1) == 33333 and pc.US(30) == 1_000_000 and isinstance(pc.US(7), int)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd ".claude/edit-mo-to/tools" && .venv/bin/python -m pytest tests/test_plan_common.py -q`
Expected: FAIL with `ModuleNotFoundError: plan_common`

- [ ] **Step 3: Create `plan_common.py` with the moved functions, unchanged bodies; in `plan_build.py` delete them and add the import line**

- [ ] **Step 4: Run the whole suite**

Run: `.venv/bin/python -m pytest tests -q -m "not slow"`
Expected: all previously passing tests pass, plus the 2 new ones

- [ ] **Step 5: Commit**

```bash
git add .claude/edit-mo-to/tools/plan_common.py .claude/edit-mo-to/tools/plan_build.py .claude/edit-mo-to/tools/tests/test_plan_common.py
git commit -m "tools: move sfx cues, beat snap and plan checks into plan_common"
```

---

### Task 2: Compact plan expander (`plan_tools.py expand`)

**Files:**
- Create: `.claude/edit-mo-to/tools/plan_tools.py`
- Test: `.claude/edit-mo-to/tools/tests/test_plan_tools_expand.py`

**Interfaces:**
- Consumes: `motion_render.list_templates()` (template var names, for brand fills).
- Produces: `expand(plan2: dict) -> dict` (the contract plan, spec §1 ↔ `style-agent-contract.md` edit-plan schema); `plan_table(plan: dict) -> str`; `sec(frame: int) -> float` (`round(frame / 30, 10)`); CLI `expand <plan2.json> [--out plan.json] [--table plan_table.txt]` printing `{"plan": path, "table": path, "timelines": n, "clips": n, "overlays": n}`.
- Contract plan additions used by later tasks: each timeline may carry `"effects": [{"name", "at", "duration"}]`; each clip may carry `"keyframes": [{"t", "scale", "x", "y"}]` (timeline seconds from the clip's `at`), `"transition_duration"`, `"gain_db"`, `"layout"`.

Row shapes (spec §1 and builder-check decisions 2, 4, 5): clip `[file, src_in_f, at_f, len_f, opts?]`; overlay `[template, at_f, len_f, vars, track, sfx, opts?]` (overlay `opts`: `on` ∈ `word` | `beat`, `cutout: true`); effect `[name, at_f, len_f]`; clip `opts` keys: `track` (`main`→`video_main`, `top`→`video_top`, `bottom`→`video_bottom`, `overlay`→`video_overlay`), `scale`, `x`, `y`, `speed`, `mute` (default `True`), `transition`, `transition_f` (default 9), `line`, `layout`, `kf` (`[[t_f, scale, x, y], …]`), `volume`, `gain_db`, `allow_scale`, `shared`. Every opt is copied to the contract clip/overlay under the same name (`on`, `shared`, `allow_scale`, `gain_db`, `cutout` included) so `check`, `build_project` and `qa_check` can read them. Blocks: `{"use": NAME, "at_f": N}` in `seq` shifts every row's `at_f` by `N`. `vo_in`/`vo_out` from `vo_in_f`/`vo_out_f`, defaults `0` and the timeline's last clip end. Brand fill: for each overlay, set `font`, `bg`, `fg`, `accent` from `plan2["brand"]` only when the template declares that var and the row's vars don't set it.

- [ ] **Step 1: Write the failing tests**

```python
def _p2(**kw):
    base = {"project": "T", "fps": 30, "width": 1080, "height": 1920, "base": "/v/",
            "brand": {"font": "Inter", "bg": "#000000", "fg": "#ffffff", "accent": "#ff0000"},
            "vo": {"file": "vo.mp3", "volume": 1.0}, "music": None, "blocks": {}, "timelines": []}
    return {**base, **kw}

def test_frames_become_ten_decimal_seconds_and_paths_join_base():
    p = pt.expand(_p2(timelines=[{"name": "T01", "seq": [{"clips": [["a.mp4", 7, 0, 107]]}]}]))
    c = p["timelines"][0]["clips"][0]
    assert c["file"] == "/v/a.mp4" and c["src_in"] == 0.2333333333 and c["src_out"] == 3.8
    assert c["at"] == 0.0 and c["track"] == "video_main" and c["mute"] is True and c["speed"] == 1.0
    assert p["timelines"][0]["vo"] == "/v/vo.mp3" and p["timelines"][0]["vo_out"] == 3.5666666667

def test_block_reuse_shifts_rows_and_is_written_once():
    body = {"clips": [["b.mp4", 0, 0, 30]], "overlays": [["badge", 0, 30, {"text": "X"}, "ui", "default"]]}
    p = pt.expand(_p2(blocks={"BODY": body}, timelines=[
        {"name": "H1", "seq": [{"clips": [["h1.mp4", 0, 0, 60]]}, {"use": "BODY", "at_f": 60}]},
        {"name": "H2", "seq": [{"clips": [["h2.mp4", 0, 0, 45]]}, {"use": "BODY", "at_f": 45}]}]))
    assert p["timelines"][0]["clips"][1]["at"] == 2.0 and p["timelines"][1]["clips"][1]["at"] == 1.5
    assert p["timelines"][0]["overlays"][0]["at"] == 2.0 and p["timelines"][0]["clips"][1]["block"] == "BODY"

def test_brand_fills_only_declared_vars_and_keyframes_convert():
    p = pt.expand(_p2(timelines=[{"name": "T", "seq": [{"clips": [["a.mp4", 0, 0, 30, {"kf": [[0, 1.0, 0, 0], [15, 1.2, 0.1, -0.1]], "transition": "Blur"}]],
                                                        "overlays": [["badge", 0, 30, {"text": "Y"}, "ui", "none"]]}]}]))
    ov = p["timelines"][0]["overlays"][0]; c = p["timelines"][0]["clips"][0]
    assert ov["vars"]["font"] == "Inter" and ov["vars"]["bg"] == "#000000" and "ring" not in ov["vars"]
    assert c["keyframes"] == [{"t": 0.0, "scale": 1.0, "x": 0, "y": 0}, {"t": 0.5, "scale": 1.2, "x": 0.1, "y": -0.1}]
    assert c["transition"] == "Blur" and c["transition_duration"] == 0.3

def test_unknown_track_and_fractional_frame_are_rejected():
    with pytest.raises(ValueError, match="track"):
        pt.expand(_p2(timelines=[{"name": "T", "seq": [{"clips": [["a.mp4", 0, 0, 30, {"track": "side"}]]}]}]))
    with pytest.raises(ValueError, match="whole frame"):
        pt.expand(_p2(timelines=[{"name": "T", "seq": [{"clips": [["a.mp4", 0, 0, 30.5]]}]}]))

def test_plan_table_has_one_row_per_clip_in_seconds_frames():
    p = pt.expand(_p2(timelines=[{"name": "T01", "seq": [{"clips": [["a.mp4", 7, 0, 107]]}]}]))
    t = pt.plan_table(p)
    assert t.splitlines()[0].startswith("# | Timeline | At | Len | File") and "| 0:00 | 3:17 |" in t
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_plan_tools_expand.py -q`
Expected: FAIL, `ModuleNotFoundError: plan_tools`

- [ ] **Step 3: Implement `expand`, `plan_table`, `sec` and the CLI in `plan_tools.py`**

`expand` validates every `at_f`/`len_f`/`src_in_f` is an `int` (raise `ValueError("... must be a whole frame")`), copies `base` and `brand` into the contract plan (later tools need `base` for snapshots and sheets), resolves blocks before timelines, writes `src_out = sec(src_in_f + len_f * speed)` (len is timeline length; source length = len × speed), `transition_duration = sec(transition_f)` when a transition is set, `keyframes[].t = sec(t_f)`. Keep the module importable without ffmpeg (no probes here).

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_plan_tools_expand.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/edit-mo-to/tools/plan_tools.py .claude/edit-mo-to/tools/tests/test_plan_tools_expand.py
git commit -m "plan_tools: expand the compact frame plan into the contract plan"
```

---

### Task 3: Plan check (`plan_tools.py check`)

**Files:**
- Modify: `.claude/edit-mo-to/tools/plan_tools.py`
- Test: `.claude/edit-mo-to/tools/tests/test_plan_tools_check.py`

**Interfaces:**
- Produces: `check(plan: dict, limits: dict | None = None, probe=probe_media, silent=edge_silent) -> list[str]` (empty = clean; each error starts with `T<n> clip <m>:` / `T<n> overlay <m>:` / `T<n> vo:`); `probe_media(path: str) -> dict` (`{"duration", "width", "height", "fps", "rotation"}`, cached as JSON in `{tmp}/probe/<sha1 of path|size|mtime>.json`); `edge_silent(path: str, t: float, window: float = 0.8, floor_db: float = -60.0) -> bool` (ffmpeg `astats` RMS over 20 ms steps, the probe qa.md prescribes); `source_overlaps(a: dict, b: dict) -> bool`; CLI `check <plan.json> [--limits limits.json]` printing `{"ok": bool, "errors": [...]}` and exit code 1 when not ok.
- `limits.json` shape: `{"min_s": 20, "max_s": 30, "caption_band_px": 400}`.

Checks (spec §2 and the builder-check decisions 3–5): whole frames; main-track gaps/overlaps; source range inside the file; reuse within a timeline, and overlapping spans across timelines except `block` rows and rows with `shared: true`; VO edges silent and `vo_out` ≤ VO duration; overlay starts on a clip `at` (±1 frame) unless the overlay has `"on": "word"` or `"on": "beat"`, and no overlap per track; template exists and `motion_render.fill(template_text, vars)` succeeds; SFX names exist in `motion/sfx/`; scale convention: `fitted = fit(upright_size, (1080, 1920))` (uniform scale to fit; swap width/height when `rotation` is ±90), "black edges" when `scale * fitted < canvas` on either axis, "above 2.0" when `scale > 2.0` without `allow_scale`; overlays with a `top`/`y` var inside the bottom `caption_band_px` fail unless template ∈ {`cta`, `end-card`, `title-card`}; `limits` min/max on the timeline end; `texts` must be empty when `limits.no_text`; any `texts` row whose `role` is caption fails. (Task 2's overlay row gains an optional 7th element `opts` with `on`; clip `opts` gain `shared`.)

- [ ] **Step 1: Write the failing tests** (inject `probe` and `silent` so no media is needed; one real-ffmpeg test for `edge_silent` on a synthetic file: 1 s silence, 1 s 440 Hz sine, 1 s silence)

```python
PROBE = lambda p: {"duration": 10.0, "width": 1080, "height": 1920, "fps": 30, "rotation": 0}
QUIET = lambda p, t, **k: True

def test_clean_plan_has_no_errors(): assert pt.check(PLAN_OK, probe=PROBE, silent=QUIET) == []

def test_reuse_within_and_across_timelines_is_reported():
    errs = pt.check(PLAN_REUSE, probe=PROBE, silent=QUIET)
    assert any("reused" in e and "T1 clip 2" in e for e in errs)
    assert any("overlaps T1 clip 1" in e and e.startswith("T2 clip 1") for e in errs)

def test_block_rows_are_exempt_from_cross_timeline_reuse(): ...   # same source span, both rows carry "block": "BODY"

def test_vo_past_end_and_loud_edge_are_reported():
    errs = pt.check(PLAN_VO_LONG, probe=lambda p: {**PROBE(p), "duration": 3.0}, silent=lambda p, t, **k: False)
    assert any("vo_out 5.0 is past the file end 3.0" in e for e in errs) and any("not silent" in e for e in errs)

def test_overlay_off_cut_and_unknown_template_and_band():
    errs = pt.check(PLAN_OVERLAYS, probe=PROBE, silent=QUIET)
    assert any("does not start on a cut" in e for e in errs)
    assert any("no template 'bagde'" in e for e in errs)
    assert any("caption band" in e for e in errs)

def test_shared_aroll_and_word_overlays_are_allowed():
    assert pt.check(PLAN_SHARED, probe=PROBE, silent=QUIET) == []   # same host file in T1 and T2 with "shared": true; overlay with "on": "word" off a cut

def test_scale_convention_with_small_source():
    small = lambda p: {**PROBE(p), "width": 576, "height": 1024}
    assert pt.check(PLAN_SCALE_OK, probe=small, silent=QUIET) == []          # scale 1.1 on a 576x1024 clip is fine
    assert any("black edges" in e for e in pt.check(PLAN_SCALE_LOW, probe=small, silent=QUIET))   # scale 0.8 full-frame
    assert any("above 2.0" in e for e in pt.check(PLAN_SCALE_HIGH, probe=small, silent=QUIET))

def test_edge_silent_on_real_audio(tmp_path):
    wav = tmp_path / "v.wav"   # ffmpeg: anullsrc 1 s + sine 1 s + anullsrc 1 s, concat
    assert pt.edge_silent(str(wav), 0.5) and not pt.edge_silent(str(wav), 1.5) and pt.edge_silent(str(wav), 2.5)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_plan_tools_check.py -q`
Expected: FAIL, `AttributeError: check`

- [ ] **Step 3: Implement `check`, `probe_media`, `edge_silent`, `source_overlaps` and the `check` CLI**

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_plan_tools_check.py -q`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/edit-mo-to/tools/plan_tools.py .claude/edit-mo-to/tools/tests/test_plan_tools_check.py
git commit -m "plan_tools: check a plan for timing, reuse, VO edges, overlays, templates and scale before QA"
```

---

### Task 4: Compact prompts expander and checker (`plan_tools.py prompts`, `check-prompts`)

**Files:**
- Modify: `.claude/edit-mo-to/tools/plan_tools.py`
- Test: `.claude/edit-mo-to/tools/tests/test_plan_tools_prompts.py`

**Interfaces:**
- Produces: `render_prompts(spec: dict, script_lines: list[str], timings: dict | None) -> str` (the deliverable: table `# | Script line | VO in | VO out | Length | Source | Prompt / Cut | Attach`, then one ```` ``` ```` block per prompt in the order Subject · Setting · Action · Camera · Look · Dialogue · Locks (full text, in `prompt["locks"]` order) · Attach · Negative, plus a Notes section from `spec["notes"]`); `check_prompts(spec, script_lines, timings) -> list[str]`; `REQUIRED_LOCKS: dict[str, list[str]]` = ugc `[realism, product, notext, voice, look, pacing]`, broll `[realism, notext]`, pixar `[style_bible, notext, voice]`, claymation `[style_bible, notext, voice]`, `product-ad` `[product, notext]`; CLI `prompts <prompts2.json> --script script.txt [--timings vo.json] --out prompts.txt` and `check-prompts <prompts2.json> --script script.txt [--timings vo.json]`.
- `prompts2` keys (spec §3) plus `"style"` (one of the five), optional `"notes"`, and per prompt `"kind": "video" | "keyframe" | "character"` (default `video`). Image kinds (`keyframe`, `character`) render the storyboard table `# | Script line | Shot | Save as` (`save_as` from the prompt's `id`, e.g. `SB-3.png`, `CHAR-1.png`) and skip the VO-length and dialogue rules; the locks still expand in full.
- `timings` is `media_timing.py vo` JSON (`lines[].start/end`, `words`); when given, `vo_in_f`/`vo_out_f` are checked against the line's span.
- `style: product-ad`: `--script`/`--timings` are optional and ignored; required locks `product`, `notext`; only the generator's length limits apply; `--beats` is accepted and ignored.

- [ ] **Step 1: Write the failing tests**

```python
def test_locks_are_expanded_in_full_in_every_prompt():
    out = pt.render_prompts(SPEC2, SCRIPT, None)
    assert out.count(SPEC2["locks"]["realism"]) == 2 and "```" in out and "| AI-1 (generate) |" in out

def test_lock_override_replaces_only_that_lock(): ...   # prompt 2 has lock_overrides.product → its block has the override, prompt 1 the default

def test_check_requires_style_locks_and_verbatim_dialogue():
    errs = pt.check_prompts({**SPEC2, "prompts": [dict(SPEC2["prompts"][0], locks=["realism"], dialogue="wrong words")]}, SCRIPT, None)
    assert any("missing locks: product, notext, voice, look, pacing" in e for e in errs) and any("dialogue" in e for e in errs)

def test_flow_limits_attach_and_length():
    bad = dict(SPEC2["prompts"][0], attach=[f"@Image{i}" for i in range(1, 9)], gen_len_s=9)
    errs = pt.check_prompts({**SPEC2, "prompts": [bad]}, SCRIPT, None)
    assert any("7 attachments" in e for e in errs) and any("4–8 s" in e for e in errs)

def test_short_span_needs_use_when_generated_longer():
    short = dict(SPEC2["prompts"][0], vo_in_f=0, vo_out_f=72, gen_len_s=4)        # 2.4 s span
    assert any("use" in e for e in pt.check_prompts({**SPEC2, "prompts": [short]}, SCRIPT, None))
    assert pt.check_prompts({**SPEC2, "prompts": [dict(short, use="0:00-2:12")]}, SCRIPT, None) == []

def test_span_must_match_timings_within_two_frames():
    timings = {"lines": [{"start": 0.0, "end": 2.5}, {"start": 2.5, "end": 6.0}]}
    off = dict(SPEC2["prompts"][0], line=1, vo_in_f=0, vo_out_f=90)                 # line 1 ends at frame 75
    assert any("±2 frames" in e for e in pt.check_prompts({**SPEC2, "prompts": [off]}, SCRIPT, timings))

def test_keyframe_kind_renders_storyboard_table_and_skips_vo_rules():
    kf = dict(SPEC2["prompts"][0], id="SB-3", kind="keyframe", vo_in_f=0, vo_out_f=1, dialogue="")
    out = pt.render_prompts({**SPEC2, "prompts": [kf]}, SCRIPT, None)
    assert "# | Script line | Shot | Save as" in out and "SB-3.png" in out
    assert pt.check_prompts({**SPEC2, "prompts": [kf]}, SCRIPT, None) == []

def test_product_ad_needs_no_script():
    spec = {**SPEC2, "style": "product-ad", "prompts": [dict(SPEC2["prompts"][0], locks=["product", "notext"], dialogue="")]}
    assert pt.check_prompts(spec, [], None) == []
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_plan_tools_prompts.py -q`
Expected: FAIL, `AttributeError: render_prompts`

- [ ] **Step 3: Implement `render_prompts`, `check_prompts`, `REQUIRED_LOCKS` and both CLIs**

Times in the table use `media_timing.to_sf`. Seedance prompts start with `Start on @Image1` when `mode == "seedance"`; Flow prompts end with the `Attach:` line.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_plan_tools_prompts.py -q`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/edit-mo-to/tools/plan_tools.py .claude/edit-mo-to/tools/tests/test_plan_tools_prompts.py
git commit -m "plan_tools: expand compact prompt specs into full prompts and check them against the script"
```

---

### Task 5: Parallel, slim, offline overlay renders (`motion_render.py`)

**Files:**
- Modify: `.claude/edit-mo-to/tools/motion_render.py` (`fill`, `render`, new `slim`, `render_many`, `job_key`)
- Create: `.claude/edit-mo-to/motion/skeleton/gsap.min.js` (download once: `curl -sSL -o .claude/edit-mo-to/motion/skeleton/gsap.min.js https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js`; verify `grep -c "3.14.2"` ≥ 1)
- Modify: `.claude/edit-mo-to/tools/machine.py` (defaults `render_workers: 1`, `render_concurrency: min(4, max(1, os.cpu_count() // 2))`)
- Test: `.claude/edit-mo-to/tools/tests/test_motion_render.py` (extend)

**Interfaces:**
- Produces: `render(name, out, variables=None, fps=30, workers: int | None = None, slim: bool = True) -> dict` (adds `--workers <n>` from `machine.json["render_workers"]`; runs `slim` after a successful render; result gains `"bytes"`); `slim(mov: Path) -> dict` (`{"before", "after", "ratio"}`; ffmpeg `-c:v prores_ks -profile:v 4444 -vendor apl0 -pix_fmt yuva444p10le -qscale:v 6 -alpha_bits 8` to `<mov>.slim.tmp.mov` beside it, then `os.replace`; on ffmpeg failure the original stays and the function raises `RenderFailed`); `job_key(template: str, variables: dict, duration: float) -> str` (sha1 of the JSON-sorted vars + template + duration); `render_many(jobs: list[dict], concurrency: int | None = None, render_fn=render) -> list[dict]` where job = `{"template", "out", "vars"}`: identical keys render once, the others are `shutil.copy2`'d; returns one dict per job with `"copied_from"` when copied; `fill()` rewrites `https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js` → `gsap.min.js`.
- CLI: `render … [--no-slim] [--workers N]`; new `render-many <jobs.json> [--concurrency N]`.

- [ ] **Step 1: Write the failing tests**

```python
def test_fill_points_gsap_at_the_local_copy():
    html = mr.fill('<!--defaults {"duration": 2} --><script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>', {})
    assert 'src="gsap.min.js"' in html and "jsdelivr" not in html
    assert (mr.MOTION / "skeleton" / "gsap.min.js").exists()

def test_job_key_ignores_var_order_and_sees_media_paths():
    a = mr.job_key("badge", {"text": "A", "bg": "#000"}, 3.0); b = mr.job_key("badge", {"bg": "#000", "text": "A"}, 3.0)
    assert a == b and a != mr.job_key("badge", {"text": "A", "bg": "#000"}, 3.5)
    assert mr.job_key("phone-cards", {"video1": "/a.mp4"}, 3) != mr.job_key("phone-cards", {"video1": "/b.mp4"}, 3)

def test_render_many_renders_duplicates_once(tmp_path):
    calls = []
    def fake(name, out, variables=None, **kw):
        calls.append(name); Path(out).write_bytes(b"x"); return {"file": str(out), "alpha": True}
    jobs = [{"template": "badge", "out": tmp_path / f"{i}.mov", "vars": {"text": "SAME", "duration": 3}} for i in range(3)]
    jobs.append({"template": "badge", "out": tmp_path / "d.mov", "vars": {"text": "OTHER", "duration": 3}})
    res = mr.render_many(jobs, concurrency=2, render_fn=fake)
    assert len(calls) == 2 and all(Path(j["out"]).exists() for j in jobs) and sum("copied_from" in r for r in res) == 2

@pytest.mark.slow
def test_slim_keeps_alpha_and_pixels(tmp_path):      # real render of badge at 2 s, path with a space
    out = tmp_path / "with space" / "b.mov"; out.parent.mkdir()
    mr.render("badge", out, {"text": "SLIM", "duration": 2}, slim=False)
    before = out.stat().st_size; info = mr.slim(out)
    assert info["after"] < before * 0.75 and mr._probe(out)["alpha"]
    # PSNR vs an unslimmed copy ≥ 58 dB: ffmpeg -i a -i b -lavfi psnr -f null -, parse "average:"

def test_slim_failure_leaves_original(tmp_path, monkeypatch):
    f = tmp_path / "x.mov"; f.write_bytes(b"not a movie")
    with pytest.raises(mr.RenderFailed): mr.slim(f)
    assert f.read_bytes() == b"not a movie" and not list(tmp_path.glob("*.tmp.mov"))
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_motion_render.py -q -m "not slow"`
Expected: the 4 new tests FAIL (`job_key`, `render_many`, `slim` missing; gsap assertion fails)

- [ ] **Step 3: Download `gsap.min.js` into `motion/skeleton/`, then implement the rewrite in `fill`, `job_key`, `render_many` (`concurrent.futures.ThreadPoolExecutor`; each `render` is its own subprocess), `slim`, the `workers` flag, and the CLI changes**

- [ ] **Step 4: Run the tests, including the slow one once**

Run: `.venv/bin/python -m pytest tests/test_motion_render.py -q` (needs the HyperFrames node_modules; fonts from cache or network)
Expected: all pass; print of the slow test shows PSNR ≥ 58

- [ ] **Step 5: Measure on this machine and record it**

Run: `time .venv/bin/python motion_render.py render badge /tmp/emt_bench/badge.mov --vars '{"text":"BENCH","duration":3}'`
Expected: wall time ≤ 5.5 s on the Mac M4 (baseline 7.3 s); write the number into `docs/edit-mo-to-speed-revamp.md` under a new "After" line.

- [ ] **Step 6: Commit**

```bash
git add .claude/edit-mo-to/tools/motion_render.py .claude/edit-mo-to/tools/machine.py .claude/edit-mo-to/motion/skeleton/gsap.min.js .claude/edit-mo-to/tools/tests/test_motion_render.py docs/edit-mo-to-speed-revamp.md
git commit -m "motion_render: one-worker renders in parallel, slim ProRes 4444 output, local GSAP"
```

---

### Task 6: Tiled frame sheets (`sheets.py`)

**Files:**
- Create: `.claude/edit-mo-to/tools/sheets.py`
- Modify: `.claude/edit-mo-to/tools/requirements.txt` (add `Pillow`), then `.venv/bin/python -m pip install Pillow`
- Test: `.claude/edit-mo-to/tools/tests/test_sheets.py`

**Interfaces:**
- Produces: `grab(video: str, t: float, out: Path, w: int = 270) -> Path` (ffmpeg `-ss t -i … -frames:v 1 -vf scale=w:-2`); `tile(frames: list[tuple[str, Path]], out: Path, cols: int = 4, rows: int = 3) -> Path` (Pillow grid, each cell labelled top-left with its string on a dark box, cell 270×480); `clip_sheets(plan: dict, timeline: str, out_dir: Path, ai: bool = False) -> dict` → `{"sheets": [{"path", "items": ["1", "2", …]}]}` using each clip's middle source time (or in/mid/out as three cells labelled `n·in`/`n·mid`/`n·out` when `ai`); `overlay_sheets(plan, timeline, out_dir) -> dict` (overlay middle frame composited on the clip under it at that time, label `ov<n>`); `inventory(folder: Path, out_dir: Path, max_clips: int | None = None) -> dict` → `{"clips": [{"path", "duration", "fps", "width", "height", "rotation", "strip"}], "sheets": [...]}` with one 6-frame strip per clip and strips tiled 6 per sheet (the cataloguing style agents redo per run today).
- CLI: `clips <plan.json> "<timeline>" <out_dir> [--ai]`, `overlays …`, `inventory <folder> <out_dir> [--max N]`, each printing the dict.

- [ ] **Step 1: Write the failing tests** (synthetic clips via ffmpeg `testsrc2=size=576x1024:rate=30:duration=4`)

```python
def test_tile_labels_and_size(tmp_path): ...        # 5 frames → one 1080x1440 sheet; pixel at (4,4) is dark (label box)
def test_clip_sheets_twelve_per_sheet(tmp_path): ...  # plan with 14 clips → 2 sheets, items ["1".."12"], ["13","14"]
def test_ai_mode_three_cells_per_clip(tmp_path): ...  # 2 AI clips → 6 cells labelled "1·in","1·mid","1·out",...
def test_inventory_lists_probe_and_strip(tmp_path): ... # 2 clips → duration 4.0, fps 30, strip png exists, 1 sheet
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_sheets.py -q`
Expected: FAIL, `ModuleNotFoundError: sheets` (and `PIL` until installed)

- [ ] **Step 3: Add Pillow to requirements, install it, implement `sheets.py`**

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_sheets.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/edit-mo-to/tools/sheets.py .claude/edit-mo-to/tools/requirements.txt .claude/edit-mo-to/tools/tests/test_sheets.py
git commit -m "sheets: tiled, labelled frame sheets for clips, overlays and clip inventories"
```

---

### Task 7: One-shot build (`build_project.py`)

**Files:**
- Create: `.claude/edit-mo-to/tools/build_project.py`
- Test: `.claude/edit-mo-to/tools/tests/test_build_project.py`

**Interfaces:**
- Consumes: `plan_common.US/sfx_cues`, `motion_render.render_many/cutout`, `capcut_project.compose/add_timeline/replace_timeline/add_tracks/import_media/wait_for_draft/segments`, `edit_diff` snapshot (call `capcut_project.segments` and write the JSON), `sheets.clip_sheets`, `machine.BUILD/TMP`.
- Produces (pure, unit-testable): `overlays_to_frames(timeline: dict) -> list[dict]` (contract overlays → `{"template","from","to","vars","sfx","track"}` in frames); `clip_body(draft_id: str, clip: dict, canvas: tuple[int, int]) -> dict` (the `add_video` JSON: integer-µs `start`/`end`/`target_start` passed as µs/1e6; `track_name` `"video"` for `video_main`; `relative_index` main 0 / top 1 / bottom 2 / overlay 1; masks for `layout` `split-top`/`split-bottom` as editor.md states: `mask_type Rectangle, mask_center 0/0, mask_size 0.5, mask_rect_width 1.0`; `volume` 0 when `mute` else `10 ** (gain_db / 20)`); `keyframe_body(draft_id, clip, track_name) -> dict | None` (`property_types` `["uniform_scale","position_x","position_y"]`, `times` = `at + t` with the first time `+ 0.001`, `values` as strings); `effect_body(draft_id, effect) -> dict` (`effect_type`, `start`, `end`, `params: []`, `track_name "effect_01"`); `vo_body(draft_id, timeline, end_frame) -> dict` (ends on `end_frame / 30`, never the file length); `build_timeline(plan, timeline, post=post, render=True) -> dict` (`{"draft": dir, "end_frame", "counts"}`; order: `create_draft`, then all overlays (they create the overlay track, which sidesteps the one-video-track `StopIteration` bug), then main-track clips, other video tracks, keyframes, effects, cutouts, VO, music, SFX cues, `save_draft`, `wait`. A timeline with no overlays depends on the VectCutAPI patch from the README; `build` checks once with `grep -c "StopIteration" {mcp_servers}/VectCutAPI/add_video_track.py` and stops with "apply the VectCutAPI StopIteration patch (README, Manual setup step 5)" when the count is 0 and any timeline has no overlays); `build(plan, import_files=(), timelines=None, job=None, post=post) -> dict` (renders all overlays of all timelines in one `render_many` call first, then timelines, then `compose`, `import_media`, snapshot per timeline to `<base>/.edit-mo-to/built/<timeline>.json`, `clip_sheets` per timeline to `{tmp}/reports/<job>/sheets/`, report at `{tmp}/reports/<job>/build_report.txt`, returns the ≤ 25-line summary dict); `timeline(plan, name, post=post) -> str` (one draft, for revisions); `music_draft(name_end_frame: int, music: str, volume: float, post=post) -> str`.
- CLI: `build <plan.json> [--import f …] [--timelines "A,B"] [--job NAME] [--no-render]`, `timeline <plan.json> "<name>"`, `music <plan.json> "<name>" --music f --volume v`; all print JSON only.

- [ ] **Step 1: Write the failing unit tests with a recording `post` stub**

```python
def _post_recorder():
    calls = []
    def post(ep, body):
        calls.append((ep, body))
        return {"success": True, "output": {"draft_id": "dfd_test"}}
    return calls, post

def test_clip_body_exact_microseconds_and_main_track_name():
    b = bp.clip_body("d", {"file": "/a.mp4", "src_in": 0.2333333333, "src_out": 3.8, "at": 1.0333333333, "speed": 1.0,
                           "track": "video_main", "x": 0, "y": 0, "scale": 1.0, "mute": True}, (1080, 1920))
    assert b["track_name"] == "video" and b["relative_index"] == 0 and b["volume"] == 0
    assert round(b["target_start"] * 1e6) == 1033333 and round((b["end"] - b["start"]) * 1e6) == 3566667

def test_split_top_gets_mask_and_half_offset():
    b = bp.clip_body("d", {**CLIP, "track": "video_top", "layout": "split-top", "y": 0.5}, (1080, 1920))
    assert b["mask_type"] == "Rectangle" and b["mask_size"] == 0.5 and b["mask_rect_width"] == 1.0 and b["transform_y"] == 0.5

def test_keyframes_nudge_first_point_and_use_timeline_seconds():
    kb = bp.keyframe_body("d", {**CLIP, "at": 2.0, "keyframes": [{"t": 0.0, "scale": 1.0, "x": 0, "y": 0}, {"t": 0.5, "scale": 1.2, "x": 0.1, "y": 0}]}, "video")
    assert kb["property_types"] == ["uniform_scale", "position_x", "position_y"] and kb["times"][0] == pytest.approx(2.001) and kb["times"][1] == 2.5

def test_effect_body_has_empty_params(): assert bp.effect_body("d", {"name": "White Flash", "at": 2.1, "duration": 0.2})["params"] == []

def test_build_timeline_order_and_vo_end_on_frame(tmp_path, monkeypatch):
    calls, post = _post_recorder()
    monkeypatch.setattr(bp.cp, "wait_for_draft", lambda p, t=30: Path(p))
    res = bp.build_timeline(PLAN, PLAN["timelines"][0], post=post, render=False)   # overlays carry prebuilt "file"
    eps = [e for e, _ in calls]
    assert eps[0] == "create_draft" and eps[1] == "add_video" and calls[1][1]["track_name"] != "video"   # overlay track first
    vo = next(b for e, b in calls if e == "add_audio" and b["track_name"] == "vo")
    assert vo["end"] == PLAN["timelines"][0]["vo_in"] + res["end_frame"] / 30 and eps[-1] == "save_draft"
    assert calls[-1][1]["auto_deploy"] is False

def test_sfx_cues_come_from_plan_common(): ...   # two overlays with sfx default → add_audio bodies on sfx_a/sfx_b, none past the end
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_build_project.py -q`
Expected: FAIL, `ModuleNotFoundError: build_project`

- [ ] **Step 3: Implement `build_project.py`** (bodies as the Interfaces block states; `post` as in `plan_build.post` but raising `RuntimeError` with the endpoint and body instead of `sys.exit`; cutouts as in `plan_build.render_overlays`)

- [ ] **Step 4: Run the unit tests**

Run: `.venv/bin/python -m pytest tests/test_build_project.py -q`
Expected: 6 passed

- [ ] **Step 5: Add one integration test behind the API check** (`_api_up()` as in `test_capcut_project.py`; skip otherwise): build a 2-timeline plan from two synthetic clips and one real template overlay into `{tmp}/_test_fixture/build_project`, then assert `capcut_project.list_timelines` shows both names, `segments()` of timeline 1 has the planned clip count + 1 overlay, the sheet PNG exists, the report file has one row per clip, and `draft_meta_info.json` → `draft_materials` lists each plan source exactly once with an absolute path (this is what lets the hand-made media-panel edit go). Clean up the composed project folder at the end.

Run: `.venv/bin/python -m pytest tests/test_build_project.py -q` (with the backend on port 9001)
Expected: 7 passed (or 6 passed, 1 skipped without the backend)

- [ ] **Step 6: Commit**

```bash
git add .claude/edit-mo-to/tools/build_project.py .claude/edit-mo-to/tools/tests/test_build_project.py
git commit -m "build_project: build a whole CapCut project from the plan in one process"
```

---

### Task 8: Mechanical build QA (`qa_check.py`)

**Files:**
- Create: `.claude/edit-mo-to/tools/qa_check.py`
- Test: `.claude/edit-mo-to/tools/tests/test_qa_check.py`

**Interfaces:**
- Consumes: `capcut_project.segments(project, name, search_dirs)` dumps (`segments[].track/track_type/at/duration/src_in/speed/volume/transform/scale/rotation/mask/size/text/source`), `plan_tools.edge_silent/probe_media/source_overlaps`.
- Produces: `check_build(plan: dict, project: Path, timelines: list[str] | None = None, changed: list[str] | None = None, limits: dict | None = None, segments_fn=None, probe=None, silent=None) -> dict` → `{"rows": [{"n", "check", "status": "FAIL"|"OPEN", "evidence", "fix", "timeline"}], "passed": int, "verdict": "PASS"|"FAIL (n issues)"|"DELTA PASS"|"DELTA FAIL (n)"}`; CLI `build <plan.json> "<project>" [--timelines "A,B"] [--changed 3,7,ov2] [--limits limits.json] [--search dir …]` and `prompts <prompts2.json> --script s.txt [--timings t.json]` (wraps `check_prompts`), printing the dict.
- Checks and their `check` names: `present` (every planned clip at its `at` ±2 frames with its length, matched on `source` + `src_in`), `extras`, `tracks_volumes`, `vo_span` (and both edges `edge_silent`), `rotation` (±90 → stored `size` must be upright; OPEN), `layout` (split masks, grid scales), `overlay_on_cut`, `reuse` (across the listed timelines, `source_overlaps`), `dead_stretch` (> 2.2 s no cut/overlay; advisory → OPEN), `talking_head_5s` (main-track clip > 5 s with no overlay/B-roll above it → FAIL), `sfx_repeat` (> 3 consecutive same file), `music_level` (plan `music_volume` outside 0.05–0.2 unless product ad → OPEN), `duration` (limits), `canvas`, `captions` (any `text` segment whose track name contains `caption`/`subtitle` → FAIL), `unknown_source` (placeholder path → FAIL). `changed` restricts `present/extras/overlay_on_cut/reuse` to those items and their neighbours and prefixes the verdict with `DELTA`.

- [ ] **Step 1: Write the failing tests with fake `segments_fn` dumps**

```python
def test_clean_build_passes(): r = qc.check_build(PLAN, Path("/p"), segments_fn=lambda p, n, s: DUMP_OK[n], probe=PROBE, silent=QUIET); assert r["rows"] == [] and r["verdict"] == "PASS" and r["passed"] >= 10
def test_missing_and_shifted_clips_fail(): ...        # one clip 3 frames late → FAIL present with "0:03 late"; one extra segment → FAIL extras
def test_placeholder_source_is_a_fail_not_a_crash(): ... # source "##_draftpath_placeholder_x_##/assets/a.mp4" → FAIL unknown_source
def test_caption_track_and_reuse_across_timelines(): ... # text seg on track "captions" → FAIL; same source span in T1 and T2 → FAIL reuse
def test_delta_limits_rows_and_marks_verdict(): r = ...changed=["3"]...; assert r["verdict"].startswith("DELTA") and all(row["check"] in {"present","extras","overlay_on_cut","reuse","vo_span"} for row in r["rows"])
def test_rotation_and_dead_stretch_are_open(): ...     # rotated source with landscape size → OPEN rotation; 3 s with no cut → OPEN dead_stretch
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_qa_check.py -q`
Expected: FAIL, `ModuleNotFoundError: qa_check`

- [ ] **Step 3: Implement `qa_check.py`**

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_qa_check.py -q`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/edit-mo-to/tools/qa_check.py .claude/edit-mo-to/tools/tests/test_qa_check.py
git commit -m "qa_check: every mechanical build-gate check as a script that reports only failures"
```

---

### Task 9: Context packs, compact timings, speech backend

**Files:**
- Create: `.claude/edit-mo-to/tools/context_pack.py`
- Modify: `.claude/edit-mo-to/tools/media_timing.py` (`transcribe` backend, `compact`, `--compact` flag)
- Modify: `.claude/edit-mo-to/tools/machine.py` (default `asr: "faster-whisper"`), `.claude/edit-mo-to/machine.example.json` (document `asr`, `render_workers`, `render_concurrency`)
- Modify: `.claude/edit-mo-to/tools/requirements.txt` (`mlx-whisper; sys_platform == "darwin" and platform_machine == "arm64"`)
- Test: `.claude/edit-mo-to/tools/tests/test_context_pack.py`, `tests/test_media_timing.py` (extend)

**Interfaces:**
- Produces: `build_pack(style: str, client: str | None = None, generator: str | None = None, root: Path = ROOT) -> str` (sections by `## ` heading from `preferences.md`: `General`, `Prompts (all generators)`, the generator's section (`Google Flow` | `Seedance`), the style's section (`UGC` | `B-roll` | `Claymation` | `Pixar` | `Product ad`), `Editing in CapCut`, `Known generation failures`; then the same headings from `my-preferences.md` under `# Editor's own rules (win on conflict)` when the file exists; then the client file under `# Client`); CLI `context_pack.py <style> [--client name] [--generator g] --out pack.md` printing `{"pack", "chars", "sections"}`.
- `media_timing.compact(report: dict) -> str`: `lines` as `n|start_sf|end_sf|matched|text` and `words` as `word|start_f|end_f` (frames at the report fps), header lines `# lines` / `# words`; CLI `vo … --compact` prints that text instead of JSON.
- `media_timing.transcribe(audio, cache=True, backend: str | None = None)`: `backend or PATHS.get("asr", "faster-whisper")`; `faster-whisper` uses `BatchedInferencePipeline(model).transcribe(..., batch_size=8, word_timestamps=True)` with `device="cuda"` when `ctranslate2.get_cuda_device_count() > 0` else `"cpu"`, `compute_type` `"float16"` on cuda / `"int8"` on cpu; `mlx` uses `mlx_whisper.transcribe(path, path_or_hf_repo="mlx-community/whisper-large-v3-turbo", word_timestamps=True)` and maps `segments[].words[]` to the same `{"word","start","end"}` list. Cache key unchanged.

- [ ] **Step 1: Write the failing tests**

```python
def test_pack_has_general_style_generator_and_failures_only(tmp_path): ...  # root with a mini preferences.md of 7 sections → pack has General, B-roll, Google Flow, Known generation failures; not UGC, not Pixar
def test_pack_adds_editor_rules_and_client(tmp_path): ...                   # my-preferences.md + clients/acme.md present → both headers present, in that order

def test_compact_lines_and_words():
    rep = {"lines": [{"line": "Hi there", "start_sf": "0:00", "end_sf": "0:20", "matched": True}], "words": [{"word": "Hi", "start": 0.0, "end": 0.3}], "total": "0:20"}
    out = mt.compact(rep)
    assert "1|0:00|0:20|1|Hi there" in out and "Hi|0|9" in out

def test_backend_selection(monkeypatch): ...  # monkeypatch PATHS["asr"]="mlx" and a fake mlx_whisper module → transcribe returns words mapped from its segments
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_context_pack.py tests/test_media_timing.py -q`
Expected: new tests FAIL (`context_pack` missing, `compact` missing)

- [ ] **Step 3: Implement `context_pack.py`, `compact`, the backend switch and the machine defaults; update `machine.example.json`**

- [ ] **Step 4: Run the tests, then one real transcription with the default backend to confirm the output shape is unchanged**

Run: `.venv/bin/python -m pytest tests/test_context_pack.py tests/test_media_timing.py -q` then `.venv/bin/python media_timing.py vo "<any VO file>" --no-cache --compact | head -5`
Expected: tests pass; the command prints `# lines` or `# words` and `word|start_f|end_f` rows

- [ ] **Step 5: Commit**

```bash
git add .claude/edit-mo-to/tools/context_pack.py .claude/edit-mo-to/tools/media_timing.py .claude/edit-mo-to/tools/machine.py .claude/edit-mo-to/machine.example.json .claude/edit-mo-to/tools/requirements.txt .claude/edit-mo-to/tools/tests/test_context_pack.py .claude/edit-mo-to/tools/tests/test_media_timing.py
git commit -m "context packs per style, compact VO timings, per-machine speech backend"
```

---

### Task 10: Last-write snapshots so hand edits are separated from agent patches

**Files:**
- Modify: `.claude/edit-mo-to/tools/capcut_project.py` (new `_save_last(project, name)`; called at the end of `compose` (per timeline), `add_timeline`, `replace_timeline`, `add_tracks`, `add_overlay`, `patch_timeline` when not dry-run)
- Modify: `.claude/edit-mo-to/tools/edit_diff.py` (`diff --last <project> <timeline> [client folder …]`)
- Test: `.claude/edit-mo-to/tools/tests/test_edit_diff.py` (extend), `tests/test_capcut_project.py` (extend)

**Interfaces:**
- Produces: `capcut_project.last_path(project: Path, name: str) -> Path` = `<project>/edit-mo-to-backups/<name>.last.json`; `_save_last` writes `segments(project, name)` there; `edit_diff` `diff --last` loads it as `built`.

- [ ] **Step 1: Write the failing tests**

```python
def test_replace_writes_last_snapshot(...): ...   # after cp.replace_timeline(...) the last.json exists and equals cp.segments(project, name)
def test_patch_dry_run_does_not_touch_last(...): ...
def test_diff_last_with_no_hand_edits_is_empty(...): ...  # edit_diff.main(["diff", "--last", project, name]) → changed == [] and patterns == []
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_capcut_project.py tests/test_edit_diff.py -q -k "last"`
Expected: FAIL, `AttributeError: last_path`

- [ ] **Step 3: Implement `last_path`, `_save_last`, the six call sites and the `--last` option**

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest tests -q -m "not slow"`
Expected: all pass (CapCut tests skip without the backend)

- [ ] **Step 5: Commit**

```bash
git add .claude/edit-mo-to/tools/capcut_project.py .claude/edit-mo-to/tools/edit_diff.py .claude/edit-mo-to/tools/tests/test_capcut_project.py .claude/edit-mo-to/tools/tests/test_edit_diff.py
git commit -m "capcut_project: snapshot every write so the learning diff sees only hand edits"
```

---

### Task 11: Learning step that drops known and declined rules (`learn.py`)

**Files:**
- Create: `.claude/edit-mo-to/tools/learn.py`
- Modify: `.gitignore` (add `.claude/edit-mo-to/learning-declined.jsonl`)
- Test: `.claude/edit-mo-to/tools/tests/test_learn.py`

**Interfaces:**
- Produces: `normalise(rule: str) -> set[str]` (lowercase word set, numbers replaced by `#`, `[client date]` tags and punctuation removed, stop words dropped); `is_known(rule: str, existing: list[str], threshold: float = 0.6) -> str | None` (returns the matching existing line or `None`; Jaccard on `normalise`); `existing_rules(root: Path) -> list[str]` (every `- ` bullet in `preferences.md`, `my-preferences.md`, each `clients/*.md`, and every `rule` in `learning-declined.jsonl`); `candidates(patterns: list[dict], notes: list[str]) -> list[dict]` (`{"rule", "section", "why"}`: a recurring pattern (`count ≥ 2` or `recurring` entry) becomes "next time" wording, e.g. pattern `b-roll:shorter … by 0:12` → rule `B-roll: cut about 0:12 shorter than the VO span`; each note becomes one rule verbatim with `why` = the note); `propose(patterns, notes, root) -> dict` → `{"proposals": [...], "dropped": [{"rule", "matches"}]}`; `decline(rule, root)`; `save(rule, section, root, client: str | None = None) -> Path` (appends under the `## <section>` heading of `my-preferences.md`, creating the file with `preferences.md`'s headings when missing, or to `clients/<client>.md`).
- CLI: `propose --patterns diff.json --notes notes.txt [--out proposals.json]`, `decline "<rule>"`, `save "<rule>" --section "B-roll" [--client name]`.

- [ ] **Step 1: Write the failing tests**

```python
def test_known_rule_is_dropped_even_with_different_numbers_and_tags():
    existing = ["- B-roll: cuts about 0:12 shorter than the VO span [Zapply 2026-10-15]"]
    assert lr.is_known("B-roll: cut about 0:09 shorter than the VO span", existing)
    assert lr.is_known("Music: duck 6 dB under the VO", existing) is None

def test_declined_rules_are_never_proposed_again(tmp_path): ...   # decline(rule) then propose(...) → rule in dropped with matches from learning-declined.jsonl
def test_candidates_from_recurring_patterns_and_notes(): ...      # pattern count 3 → one rule in "B-roll"; note → rule with why
def test_save_creates_my_preferences_with_sections(tmp_path): ... # my-preferences.md gets the same "## " headings as preferences.md and the rule under "## B-roll"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_learn.py -q`
Expected: FAIL, `ModuleNotFoundError: learn`

- [ ] **Step 3: Implement `learn.py` and add the gitignore line**

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_learn.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/edit-mo-to/tools/learn.py .claude/edit-mo-to/tools/tests/test_learn.py .gitignore
git commit -m "learn: propose only rules the editor does not already have or has declined"
```

---

### Task 12: Revision ops generator (`plan_tools.py ops`)

**Files:**
- Modify: `.claude/edit-mo-to/tools/plan_tools.py`
- Test: `.claude/edit-mo-to/tools/tests/test_plan_tools_ops.py`

**Interfaces:**
- Consumes: `capcut_project.segments()` dump (`segments[].id/source/src_in/at/duration/track`), `capcut_project.py patch` op shapes (`{"op": "set", "id", ...fields}`, `{"op": "remove", "id"}`, `{"op": "insert", "track", "file", "src_in", "at", "duration", ...}`; see `_Patcher` in `capcut_project.py:773-1000` for the accepted fields).
- Produces: `ops(old_plan: dict, new_plan: dict, timeline: str, dump: dict) -> dict` → `{"ops": [...], "unmapped": [{"row", "why"}]}`; CLI `ops <old_plan.json> <new_plan.json> "<timeline>" --segments dump.json [--out ops.json]`. `new_plan` is the expanded contract plan of the revised `plan2`. Matching: each old clip row → the dump segment with the same `source` (path compare after `/`-normalising) and `src_in` within 1 frame on the same track; a changed `at`/`duration`/`scale`/`x`/`y`/`speed`/`volume` becomes one `set`; an old row with no new row becomes `remove`; a new row with no old row becomes `insert`; an old row whose segment cannot be found goes to `unmapped` (the editor runner reports it; nothing is guessed). Overlays and SFX are not diffed here (they go through `add-overlay`/`add-tracks` as today).

- [ ] **Step 1: Write the failing tests**

```python
def test_moved_and_trimmed_clip_becomes_one_set_op(): ...        # clip 2 at 1.0→1.5 and duration 2.0→1.5 → [{"op":"set","id":"SEG2","at":1.5,"duration":1.5}]
def test_removed_and_added_rows(): ...                           # old clip 3 gone → remove SEG3; new clip → insert with file/src_in/at/duration/track
def test_unmappable_row_is_reported_not_guessed(): ...           # old clip whose source is a placeholder path → in unmapped, no op for it
def test_identical_plans_give_no_ops(): assert pt.ops(PLAN, PLAN, "T01", DUMP)["ops"] == []
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_plan_tools_ops.py -q`
Expected: FAIL, `AttributeError: ops`

- [ ] **Step 3: Implement `ops` and the CLI**

- [ ] **Step 4: Run the tests, then a dry run against a real project** (any existing CapCut project built by edit-mo-to: expand its plan2 twice with one `at_f` changed, run `ops`, then `capcut_project.py patch "<project>" "<timeline>" ops.json --dry-run`).
Expected: 4 passed; the dry run reports one `set` op and no validation error

- [ ] **Step 5: Commit**

```bash
git add .claude/edit-mo-to/tools/plan_tools.py .claude/edit-mo-to/tools/tests/test_plan_tools_ops.py
git commit -m "plan_tools: turn a plan revision into capcut_project patch ops"
```

---

### Task 13: Style agents write compact specs and check them (contract + 5 agents)

**Files:**
- Modify: `.claude/edit-mo-to/style-agent-contract.md` (sections "Before you write anything", "Output: mode prompts", "Output: mode edit-plan", "Hand-back")
- Modify: `.claude/agents/ugc.md`, `broll.md`, `claymation.md`, `pixar.md`, `product-ad.md` (first paragraph: read the context pack instead of preferences + my-preferences + client; edit-plan and prompts output rules)

**Interfaces:**
- Consumes: Task 2–4 CLIs, Task 6 `sheets.py inventory`, Task 9 `context_pack.py` and `--compact`.
- Produces: agents that hand back `plan2.json` + `plan.json` + `plan_table.txt` (edit-plan) or `prompts2.json` + `prompts.txt` (prompts) in `{tmp}/reports/<job>/`, with `check` / `check-prompts` clean.

Content to write (exact rules the files must contain):
- "Before you write anything": read the one file `pack` named in the dispatch (`{tmp}/reports/<job>/pack_<style>.md`) and the client file only if the pack lacks a Client section; the brief wins over the pack. If the dispatch names `inventory`, use its clips and strips; never ffprobe or render strips for clips already in it.
- `mode: edit-plan` output: write `plan2.json` in the spec §1 format (the contract's JSON block is replaced by the plan2 example and the row shapes from Task 2), then run `plan_tools.py expand plan2.json --out plan.json --table plan_table.txt` and `plan_tools.py check plan.json [--limits limits.json]`; fix and re-run until `ok: true`; hand back the three paths and the `check` output. Never type `plan.json` or the table yourself. Shared body: write it once as `blocks.BODY` and `use` it.
- `mode: prompts` output: write `prompts2.json` (spec §3 with `style`), run `plan_tools.py prompts … --out prompts.txt` and `plan_tools.py check-prompts …`; fix until clean; hand back both paths. The lock texts are written once in `locks`, in full, following the brief; never shortened in `prompts.txt`.
- Hand-back ≤ 20 lines: paths, decisions for the user, brief rules that could not be met. No tables, no prompts in the message (the main session shows `prompts.txt` and `plan_table.txt`).
- Re-runs: edit the existing `plan2.json`/`prompts2.json` rows by `#`, re-run the tools, report only the changed `#`s.

- [ ] **Step 1: Edit the contract and the five agent files as above; keep every style rule they hold today**

- [ ] **Step 2: Verify the text references only CLIs that exist**

Run: `grep -ho "plan_tools.py [a-z-]*\|sheets.py [a-z]*\|context_pack.py" .claude/edit-mo-to/style-agent-contract.md .claude/agents/*.md | sort -u`
Expected: exactly `plan_tools.py check`, `plan_tools.py check-prompts`, `plan_tools.py expand`, `plan_tools.py prompts`, `sheets.py inventory`, `context_pack.py`

- [ ] **Step 3: Dry run the `broll` agent on real footage** (from the main session): build the pack (`context_pack.py broll --client wondermint --generator google-flow --out {tmp}/reports/dryrun/pack_broll.md`), the inventory (`sheets.py inventory "{root}/Wondermint/clips" {tmp}/reports/dryrun/inv`), compact timings for `Wondermint/vo/ad1_takeA.mp3`, and dispatch `broll` in `mode: edit-plan` with the Wondermint ad-1 script.
Expected: the agent's hand-back is ≤ 20 lines; `{tmp}/reports/dryrun/plan.json` exists; `plan_tools.py check` prints `ok: true`; the agent made no ffprobe/ffmpeg strip calls (check its transcript for `ffprobe`: 0 hits).

- [ ] **Step 4: Commit**

```bash
git add .claude/edit-mo-to/style-agent-contract.md .claude/agents/ugc.md .claude/agents/broll.md .claude/agents/claymation.md .claude/agents/pixar.md .claude/agents/product-ad.md
git commit -m "style agents: compact plan and prompt specs, self-checked before hand-back"
```

---

### Task 14: Editor runner, QA on sheets, skill orchestration, learning reference

**Files:**
- Modify: `.claude/agents/editor.md` (frontmatter `model: sonnet`, `maxTurns: 40`; body rewritten around `build_project.py`)
- Modify: `.claude/agents/qa.md` (gate `build` uses `qa_check.py` + sheets; gate `prompts` uses `qa_check.py prompts` + meaning; frontmatter `effort: low` is NOT set)
- Modify: `.claude/skills/edit-mo-to/SKILL.md`, `.claude/skills/edit-mo-to/reference/steps.md`, `.claude/skills/edit-mo-to/reference/learning.md`
- Modify: `.claude/edit-mo-to/preferences.md` ("Editing in CapCut": overlays rendered slim and offline, nothing else), `docs/edit-mo-to-design.md` (Agents + Constraints paragraphs), `README.md` ("What's inside" table rows for the new tools)

Content to write:
- `editor.md`: actions `build` → `build_project.py build plan.json --import … --job <Product>`; `revise-new-timeline` → `build_project.py timeline` + `capcut_project.py add-timeline`; `revise-in-place` → `edit_diff.py diff --last` first (report hand edits), then for timing/swap/scale changes `plan_tools.py ops old_plan.json new_plan.json "<timeline>" --segments dump.json --out ops.json` → `capcut_project.py patch … --dry-run` → `patch` (report `unmapped` rows as manual steps), and only for new clips or layout changes `timeline` + `replace`; `add-music` → `build_project.py music` + `add-tracks`. Keep: ProjectBusy wording, backend health check, "never replace a captioned timeline", `add-overlay`/`add-tracks` for post-caption additions, transitions via `patch`. Remove: per-clip JSON bodies, per-overlay render loop, per-clip self-check reads (replaced by: Read each sheet in the summary's `sheets` list once), the media-panel hand edit, the hand-written placed-clips table. Report ≤ 20 lines: the summary dict's fields.
- `qa.md` gate build: run `qa_check.py build … [--changed …]`, then Read the sheets listed in `{tmp}/reports/<job>/sheets/` (clips, `--ai` for AI clips, overlays) and judge only: clip fits its line, AI slop, baked-in text/wrong product/wardrobe/blur, face/mouth/label clear; brief-checklist rows that need reading. Report = `qa_check` rows + pixel rows; never re-grab frames the sheets cover. Gate prompts: `qa_check.py prompts` first, then meaning/brief rows only. Delta = `--changed`.
- `SKILL.md`: at step 2, after the checklist is confirmed, write `{tmp}/reports/<job>/limits.json` (`min_s`, `max_s`, `ratio`, `fps`, `caption_band_px` 400, `no_text`; only keys the brief fixes); before step 3 write the pack (`context_pack.py`) once per job and the inventory once (`sheets.py inventory`) when client B-roll exists; pass `pack`, `inventory`, `timings` (compact) and `limits` paths in every dispatch; step 6 and 7 dispatch one style agent per timeline/ad and one QA per timeline in one message; step 7 order: `plan_tools.py check` (skill refuses to go on with errors) → `editor` build → `qa_check.py` → `qa` (sheets) → fixes as `patch`/delta; step 9: hand-edit diff `--last` before any write, "quit CapCut" asked once per round; "Keep agent output small" stays; the note about `CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL=1h`. Prompts are shown by pasting `prompts.txt` (unchanged rule). Gate list and wording untouched.
- `steps.md` dispatch templates: add `pack`, `inventory`, `timings_compact`, `limits` fields; remove inline `vo_timings` words list; the editor template gains `old_plan`/`new_plan`/`segments` for `revise-in-place`.
- `style-agent-contract.md` (schema section): list the new contract fields from spec decision 2 (`keyframes`, `transition_duration`, `gain_db`, `allow_scale`, `block`, `shared`, `on`, timeline `effects`).
- `learning.md`: step 1 uses `edit_diff.py diff --last …`; step 2–3 use `learn.py propose` and show only `proposals` (with `dropped` as one line "n rules you already have were skipped"); approved → `learn.py save`, declined → `learn.py decline`.

- [ ] **Step 1: Make the edits**

- [ ] **Step 2: Validate frontmatter and references**

Run: `for f in .claude/agents/*.md; do head -1 "$f" | grep -q '^---$' || echo "BAD $f"; done; grep -l "json.dump" .claude/agents/editor.md; grep -c "⛔" .claude/skills/edit-mo-to/SKILL.md`
Expected: no `BAD` lines; `editor.md` no longer matches `json.dump`; the ⛔ count equals the count on `git show HEAD:.claude/skills/edit-mo-to/SKILL.md | grep -c "⛔"`

- [ ] **Step 3: Run `/practice-muna` end to end on this machine** (the user sends a clip); at each stop accept the suggested answer.
Expected: the build step ends in one `build_project.py` call; QA reads ≤ 4 images; the learning step shows no rule already present in `preferences.md`; CapCut opens the project with overlays and SFX. Note the wall time of the build + QA stops in the handoff doc.

- [ ] **Step 4: Commit**

```bash
git add .claude/agents/editor.md .claude/agents/qa.md .claude/skills/edit-mo-to/SKILL.md .claude/skills/edit-mo-to/reference/steps.md .claude/skills/edit-mo-to/reference/learning.md .claude/edit-mo-to/preferences.md docs/edit-mo-to-design.md README.md
git commit -m "workflow: thin editor runner, QA on sheets and qa_check, parallel dispatch, dedupe learning"
```

---

### Task 15: Windows measurement and machine fixes

**Files:**
- Modify: `docs/edit-mo-to-speed-revamp.md` ("Windows findings" + "After" numbers)
- Modify: `README.md` (Windows section: Defender exclusions, CUDA note, `machine.json` keys)
- Modify (on the PC only, untracked): `.claude/edit-mo-to/machine.json`

Run on the Windows PC, in order; write every number into the handoff doc:

- [ ] **Step 1: Hardware and disks**

Run (PowerShell): `Get-CimInstance Win32_Processor | select Name,NumberOfCores; (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB; Get-CimInstance Win32_VideoController | select Name; Get-PhysicalDisk | select FriendlyName,MediaType`
Expected: the four values recorded

- [ ] **Step 2: Overlay render before/after**

Run: `python motion_render.py render badge %TEMP%\b.mov --vars "{\"text\":\"BENCH\",\"duration\":3}"` timed with `Measure-Command`, once with `render_workers` unset and once with `machine.json` `"render_workers": 1`; note whether the HyperFrames log says `screenshot` or `drawelement` capture.
Expected: the second run faster; both numbers recorded

- [ ] **Step 3: Speech**

Run: `python -c "import ctranslate2;print(ctranslate2.get_cuda_device_count())"` and `Measure-Command { python media_timing.py vo <a VO file> --no-cache }`
Expected: CUDA count and the seconds recorded; if CUDA > 0, confirm the batched cuda path is used (log line)

- [ ] **Step 4: Build area and Defender**

Run: `Get-MpPreference | select -Expand ExclusionPath`; then time one `build_project.py build` of the practice plan with and (if the editor agrees, as administrator) without `Add-MpPreference -ExclusionPath "<tmp>" ,"<root>\.claude\edit-mo-to\tools\.venv"`.
Expected: both times recorded; the README Windows section gets the `Add-MpPreference` line with the two paths as the recommended one-time step

- [ ] **Step 5: Agent waits on Windows**

From the Windows Claude transcripts (`%USERPROFILE%\.claude\projects\D--Video-Editing\`), list the last editor, QA and style-agent runs with start/end times before the revamp; record them next to the Mac numbers.

- [ ] **Step 6: Set `machine.json` on the PC** (`asr`, `render_workers: 1`, `render_concurrency` = cores/2 capped at 4) and re-run Steps 2–3.

- [ ] **Step 7: Commit the doc and README only**

```bash
git add docs/edit-mo-to-speed-revamp.md README.md
git commit -m "docs: Windows findings and setup for the speed revamp"
```

---

### Task 16: Acceptance on a real job size

**Files:**
- Modify: `docs/edit-mo-to-speed-revamp.md` ("After" table)

- [ ] **Step 1: Re-run the Wondermint ad-1 pipeline from the prompts gate with the new workflow** (brief, script, VO and clips already exist; the project name `Wondermint speed test`): style agent `edit-plan` → `check` → build → `qa_check` → QA.
Expected, measured by file mtimes as the baseline was: plan ≤ 3 min (was 7), build ≤ 4 min (was 12), build QA ≤ 3 min (was 8); zero fix rounds for timing/scale; `qa_check` rows contain no `present`/`vo_span` FAILs.

- [ ] **Step 2: Compare the overlay files** of the test build with the Wondermint originals in `Wondermint/motion/` (same template and vars): `ffmpeg -i old.mov -i new.mov -lavfi psnr -f null -` ≥ 58 dB, and the new file ≤ 65% of the old size.

- [ ] **Step 3: Write the before/after table into the handoff doc, delete the test project from CapCut's drafts folder after asking the editor, and commit the doc.**

```bash
git add docs/edit-mo-to-speed-revamp.md
git commit -m "docs: before/after numbers for the speed revamp"
```
