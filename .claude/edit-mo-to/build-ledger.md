# SDD ledger — plan: D:\Video Editing\docs\plans�6-10-15-edit-mo-to.md
Ruling: no git/worktree/commits — folder holds large client media and is not a repo; plan already says no commits — cost if wrong: no rollback history
Pre-flight: Task 4/5 share edit-plan JSON schema (defined in Task 4); Task 5 editor consumes Task 1 CLI; Task 4 consumes Task 2 CLI — consistent
Ruling: backups go in <project>dit-mo-to-backups\ not Timelines\ — extra folders inside Timelines\ could confuse CapCut — cost if wrong: none functionally
Ruling: busy check ignores our own writes via .edit-mo-to-last-write stamp — otherwise back-to-back tool calls fail for 10s — cost if wrong: a CapCut write within 10s of ours goes undetected
Task 1: complete (tests: pytest tests → 11 passed; manual CapCut open check deferred to Task 7)
Task 2: Ruling: test_align_lines_basic expected end 1.9 was a test arithmetic error — corrected to 2.4 — cost if wrong: none
Task 2: Ruling: beats snapped to nearest onset (<=70ms) with hop 128 — librosa grid drifted 2% — cost if wrong: slightly off beats on soft-attack music
Task 2: Ruling: decode audio via ffmpeg, not PyAV — faster-whisper loader crashes on current av — cost if wrong: none
Task 2: complete (tests: pytest tests → 21 passed; real VO check OK)
Task 4: complete (5 style agents + contract; broll dry run pending)
Task 5: Ruling: added capcut_project.py replace (auto-backup in-place) with test — agent-side JSON surgery too error-prone — cost if wrong: none
Task 5: Ruling: editor uses VectCutAPI HTTP API as primary route — MCP tools do not expose masks needed for split screens — cost if wrong: none, MCP kept as fallback
Task 6: complete (SKILL.md, steps.md, learning.md, CLAUDE.md; frontmatter validated; live load check deferred — CLI not authenticated)
Task 5: editor dry run built "edit-mo-to agent test" (2 timelines, split masks accepted); fixed editor.md: auto_deploy false, video_url/audio_url, mask centre 0/0, fps note, text presets, frame self-check, health check via GET
Task 5: Ruling: stray dfd_cat_* projects in CapCut drafts (from my earlier tests, auto_deploy default) left in place pending user OK to delete
Task 4: broll dry run OK (7 client clips, words-fit, split, caught scoop-vs-capsule script conflict); fixed contract: path fallback, shortlist cataloguing + tile strips, word-level cuts, min-length rule, prompts only for gaps, table standard; zapply client path corrected
Task 2: Ruling: vo output now always includes word timings (vo_report) — agents need mid-line cut points — tests 24/24
Task 7: pending user (rehearsal needs CapCut checks)
Final: fixed C1 music after captions would wipe edits — add_tracks + editor add-music action — test_add_tracks_merges_audio_and_keeps_existing_edits RED→GREEN
Final: fixed C2 hook timelines got whole VO — vo_in/vo_out per timeline in contract + editor add_audio start/end; QA checks span (instruction fix, no code)
Final: fixed I1 busy check — refuses while CapCut.exe runs + timeline file mtimes — test_busy_when_capcut_running, test_busy_when_a_timeline_file_was_just_edited RED→GREEN
Final: fixed I2 external media paths redirected — rewrite only when file exists in project assets — test_rewrite_leaves_external_paths_alone RED→GREEN
Final: fixed I3 duplicate timeline names — test_duplicate_timeline_names_refused RED→GREEN
Final: fixed I4 half-built project on failed compose — atomic temp build + rename — test_failed_compose_leaves_nothing RED→GREEN
Final: fixed I5/I6 hand edits + QA matching — segments command (original remote_url) used by editor diff and QA — test_segments_lists_original_files RED→GREEN
Final: fixed I7 grid double-crop — grids scale only, masks for splits only (instruction fix)
Final: fixed M2 (re-graded Important: spec says m:ss:ff past 60s) — test_to_sf cases RED→GREEN
Final: fixed M3/M7/M8/M9 (re-graded Important: spec/flow violations) — music path in dispatch, add_subtitle tool removed, music_volume 0.1 (~-20dB), ask new name when taken
Final: fixed M6 unsafe names — test_unsafe_project_name_refused RED→GREEN
Final: minor (deferred): M1 line matching can jump far ahead (unmatched lines already surfaced to user)
Final: minor (deferred): M4 two backups within the same second collide; no restore command (restore = copy backup folder back)
Final: minor (deferred): M5 writes are not atomic (crash mid-write could corrupt a timeline JSON; backups exist for revisions)
Final: minor (deferred): M10 CLI print encoding — mitigated by PYTHONIOENCODING=utf-8 in agent instructions
Final: Ruling: M11 test-project cleanup — needs user OK; asked at handoff — cost if wrong: clutter in CapCut list
Final: Ruling: declined-to-judge CapCut runtime items (duplicate keeps material ids, add-tracks merge, meta not updated on add) — verified only by user opening in CapCut during rehearsal — cost if wrong: a revision/music timeline may not open; backups exist

Rehearsal (Zapply Rehearsal, 2026-10-15): user verified in CapCut 9.6 — build (2 timelines), revise-new-timeline, revise-in-place, add-music on a captioned timeline (captions kept). Fixed capcut_project.py: read newer of draft_content/draft_info (CapCut saves draft_content only), write both root files; 37 tests pass. Instruction fixes: SKILL (brief pre-supplied, reuse existing VO), qa (vo edge by RMS, OPEN status, rotation, -nostdin, cut length flexible), editor (json.dump, frame-snap, relative_index, no fade, -nostdin), contract (n/30 times), steps (no extra backup), prefs/zapply/broll (cut length follows mood). Open: segments fields + placeholder paths, add-tracks asset path, rotation handling, list usage.
