# Edit Mo To GUI: build progress and handoff

Plan: `docs/superpowers/plans/2026-10-27-gui.md`. Spec: `docs/superpowers/specs/2026-10-27-gui-design.md`.
Built task by task (subagent-driven: one implementer and one reviewer per task). Paused on 2026-10-27 so Joshua can continue on the Mac.

## Status

| Task | What | State | Commits |
|---|---|---|---|
| 1 | `run` launcher, project allowlist, `.gitattributes` | done, reviewed | 3280a75..ca84b1b |
| 2 | `gui/jobstate.py` (job state, inbox, listening heartbeat) | done, reviewed (1 fix round) | ca84b1b..27daf12 |
| 3 | `gui/job.py` CLI, `gui/adapters.py` | done, reviewed (1 fix round) | 27daf12..7b8c971 |
| 4 | `gui/wait.py` | done, reviewed (1 fix round) | 7b8c971..2b8eaa9 |
| 5 | `gui/folders.py`, `gui/checks.py`, macOS CapCut check | done, reviewed (1 fix round) | 2b8eaa9..c1a3319 |
| 6 | `gui/server.py`, `gui/feedback.py` | done, reviewed (1 fix round) | c1a3319..7abadba |
| 7 | `gui/launch.py` | done, reviewed (2 fix rounds) | 7abadba..525cb51 |
| 8 | front-end shell, theme, Dashboard, Settings, `gui/demo.py`, fonts | **committed, NOT reviewed** (review was stopped at the pause) | 525cb51..4656bda |
| 9 | step pages and dialogs | not started | |
| 10 | storyboard page, `storyboard.py` fields | not started | |
| 11 | skill, agents and README updates | not started | |
| 12 | end-to-end check with Joshua (`/practice-muna` on a fresh clone) | not started | |

## Next steps

1. Review Task 8 (diff 525cb51..4656bda, font binaries excluded). Focus: XSS (text reaching innerHTML unescaped), gate answers send the right event and never advance a gate client-side, listening wording only from verified `listening`, the server.py change that returns the last 200 inbox events, dashboard polling cost, upload pre-checks, exact theme tokens, branding and verse.
2. Then Tasks 9, 10 and 11 can run **in parallel** (different files): each in its own branch from the reviewed Task 8, each with its own review, then merge. Tasks 9 and 10 put their styles in their own CSS files instead of editing `app.css`, to keep merges clean.
3. Final whole-branch review (most capable model), using the deferred list below, then Task 12 with Joshua.

**Open question for Joshua (asked 2026-10-27, not answered yet):** let the editor work early on steps that don't depend on earlier ones ("Open now" / "Waits for: X" in the sidebar). Proposed table: Brief any time; Script (paste own) any time; Voiceover upload any time; B-roll source and generator answers any time; Clips folder any time; Captions choice any time; Music choice or upload any time; everything else waits. Early answers are saved and Claude confirms them instead of asking again; gates keep their order. If yes, update the spec and add it to Tasks 9 and 11 before starting them.

## Decisions made during the build (keep these)

- `run` stays LF (`.gitattributes`); allow rule `Bash(.claude/edit-mo-to/run *)`; confirm the rule form in Task 12.
- Current job: `jobstate.set_current/get_current`, file `<tmp>/gui/current.json`; env `EDIT_MO_TO_GUI_TMP` overrides tmp (used by tests).
- Gate shape: `{"id","title","detail"?,"questions":[{"id","text","why"?,"kind","options"?,"default"?}]}`, at least one question; kinds choice, multi, text, confirm, file.
- Listening = heartbeat: `wait.py` rewrites `listening.json` ("beat") every poll; `listening(folder, max_age=10.0)` is None unless the pid is alive and the beat is fresh. The ETag ignores the beat.
- The server writes only into real video folders (`folders.is_video_folder`); `/api/job` gives 403 for others and 404 without job.json. `/api/temp-en` may also read under `capcut_drafts` (read-only, that route only).
- The front end must check upload type and size first (the server closes early on 413/415).
- The launcher only ever restarts an old-version copy of our own server (ping answers `edit-mo-to-gui` with another version); otherwise it never kills a process. A lock file serializes launches.
- Task 9: the CapCut banner keys on a gate question with id `capcut_closed`; Task 11 must use that id at every gate before a CapCut write.
- Task 11: step-tagged activity log lines use a `[step] ` prefix (job.py log has no --step).
- Task 12 is run with Joshua answering gates; a subagent can't drive it.

## Deferred minor findings (for the final review to triage)

- `run`: set `LC_ALL=C`; exit 3 with a clear message when the venv is missing; more tests (valid gui name, no args, direct exec).
- jobstate: Windows `pid_alive` returns False on access-denied (POSIX True); no concurrent-append test; a complete but unterminated last event is truncated by the next append; `listening()` misses OverflowError/NaN beat; U+2028/2029 not tested directly.
- job.py: optional fields (script `en`, row `status`/`note`) not type-checked; `--from` adapter output not validated; weak cuts/prompts adapter assertions.
- wait.py: a corrupt middle inbox line kills the waiter with a traceback; a one-`os.replace` take-over window remains (no event loss).
- server.py: about 615 lines (split routes out?); no Range support on `/api/file`.
- launch.py: the rename-back of a not-stale lock can lose exclusion on POSIX with 3+ simultaneous launchers (restore with `os.link`); POSIX kill/start paths untested.
- Tests: some GUI tests are timing-sensitive under heavy load; `test_stale_lock_taken_over_by_exactly_one` failed 1 of 3 runs once.
- Task 8 (from its implementer): `app.js` 490 lines (dialogs go to a new `dialogs.js`); the dashboard polls `/api/job` for up to 12 videos every 5 s.

## Known pre-existing test failures (not caused by this work)

`tests/test_capcut_project.py::test_segments_maps_placeholder_by_vectcut_hash`, `::test_link_originals_points_timelines_at_imported_files`, `::test_compose_can_link_originals` need client footage under `{root}/zapply`, which isn't in git. They fail in any fresh clone, including the Mac.

## Continuing on the Mac

```bash
git -C "<your Video Editing folder>" fetch origin
git -C "<your Video Editing folder>" worktree add .claude/worktrees/feat-gui feat/gui
```

Run tests from `.claude/edit-mo-to/tools/` with `.venv/bin/python -m pytest tests -q -m "not slow"` (the worktree needs the tools `.venv`: symlink it from the main checkout, `ln -s "<main>/.claude/edit-mo-to/tools/.venv" .claude/worktrees/feat-gui/.claude/edit-mo-to/tools/.venv`). On the Mac, also confirm the macOS-only paths no Windows run covered: `pgrep` CapCut check, POSIX launch kill/start, the SIGTERM test in `test_gui_wait.py`.
