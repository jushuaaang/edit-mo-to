# Edit Mo To GUI (design)

## Intent and why

edit-mo-to runs as a conversation today. Claude walks the editor through the 12 gated steps in chat, sends the heavy work to the style, `editor` and `qa` agents, and shows clip lists, prompts, plans and QA results as chat tables. It works, but it is hard to follow for a new editor: the state of the job lives only in the chat, prompts have to be found and copied out of long messages, the storyboard is a static HTML page, and every gate answer is a typed reply.

The GUI is a local web app that makes the same workflow easier to see and answer. Each step gets its own page, with the step's inputs, Claude's output, the gate question with buttons, and a text box. It is a **front end on top of the existing workflow, not a replacement**. The skill, the agents, the tools, the gates and their order stay as they are. Claude still does the work in the Claude Code session; the GUI shows it and carries the editor's answers back.

It is for Joshua and for the other editors who install edit-mo-to from the GitHub repo (`jushuaaang/edit-mo-to`), on Windows and macOS.

Requirements came from a ChatGPT-written spec (sections 1–6) and the conversation with Joshua on 2026-10-27. Where the spec and the repo disagreed, the repo and Joshua's answers win; the differences are listed under "Decisions that differ from the spec".

## Goals

- A polished local GUI, "Edit Mo To by Joshua Calonge", for every step of `/edit-mo-to` (and `/practice-muna`, which runs the same steps).
- Every ⛔ gate is shown on its step's page and answered there (buttons, fields, a text box), and Claude carries on by itself after the answer, without the editor switching to chat.
- The job's state is saved on disk, so the dashboard shows every video, its step and what waits on the editor, and it survives closing the app or the session.
- The storyboard becomes an editable grid where each shot's prompt can be copied, and keyframes are added by dropping images on the cards.
- Nothing new for an editor to install: Python from the existing tools `.venv`, plain HTML/CSS/JS, no Node build. "update edit-mo-to" (`git pull`) is enough to get a new version.
- Settings and a setup check replace hand-editing `machine.json`.

## Non-goals

- Replacing Claude Code or the chat. The chat stays open and keeps working (see "How Claude and the GUI talk").
- Running Claude or the agents from the GUI's server (no Agent SDK, no API key).
- Generating clips, voiceovers, images or music; exporting the video. Those stay the editor's (the GUI says so on those steps).
- Public hosting, accounts, logins or multi-user sync. One editor, one computer, `127.0.0.1` only.
- Word-by-word animated captions (as today).
- A `/edit-na-tayo` command (the spec named it; it does not exist in the repo).

## Anti-goals (failure even if it "works")

- The GUI lets the workflow move past a ⛔ gate the editor has not answered.
- The GUI shows a step, build, check or file as done when the tool has not actually finished and verified it (the spec's "do not pretend").
- The GUI says "Claude is listening" when no Claude session is waiting for it.
- An answer or edit typed in the GUI is lost silently (for example, sent while Claude was not listening and never picked up).
- The editor's own CapCut edits are lost or overwritten (the existing busy check, backups and `edit_diff` stay in force).
- Client files, job state or personal files get committed to the repo.
- Any name other than Joshua Calonge's appears in the app's branding.
- The GUI becomes a second copy of the workflow's rules, so that changing the skill means also changing the GUI.

## Constraints

- The 12 steps, their order, their gates and their wording in `.claude/skills/edit-mo-to/SKILL.md` and `reference/steps.md` stay. The only workflow change is the storyboard order (below).
- `CLAUDE.md` rules stay in force: times in `seconds:frames` (30 fps), full paths, 9:16 default, the user exports, no captions before step 10 except `TEMP_EN_delete_me`, deliverables shown as tables in chat.
- Every CapCut write still goes through `capcut_project.py` (busy check, backup, last-write snapshot). The GUI never writes to a CapCut project.
- Machine paths come from `.claude/edit-mo-to/machine.json` via `tools/machine.py` (Windows and Mac defaults).
- `.gitignore` already tracks only the workflow (`/docs/`, `/.claude/agents|skills|edit-mo-to/`) and ignores video folders. GUI code goes under `.claude/edit-mo-to/gui/`, job state goes in the video folders.
- Python 3.12 from the tools `.venv`; ffmpeg on PATH. No new required Python package (the standard library's `http.server` is enough); a small one may be added to `requirements.txt` only if the builder finds a real need.
- Windows and macOS, Claude Code desktop (browser pane) first; the plain Claude Code CLI with a normal browser also works.

## Approaches considered

1. **Companion GUI next to the Claude session (picked).** A small local server shows job state that Claude writes to disk, and records the editor's answers for Claude to pick up. Claude keeps doing all the work in the session. Keeps the skill, agents and tools; uses the editor's existing Claude Code (no API bill); the chat still works when the GUI is closed. Costs: two panes side by side, and a file-based hand-off that has to be made reliable.
2. **Standalone app that runs Claude itself** (Agent SDK inside the server). Most polished, one window. Rejected: a much bigger build, every gate re-wired as app logic, likely needs a paid API key, and it moves away from Claude Code Desktop, which is where editors run the workflow.
3. **Viewer only.** Pages render the job's report files and an editable storyboard; all answers still in chat. Cheapest, but it does not make the flow easier to answer, which is the point.

Joshua picked approach 1, matching the spec's "frontend and orchestration layer for the existing system".

## How it fits together

```
 Claude Code session (skill + agents + tools)          GUI server (127.0.0.1)            Browser pane
 ───────────────────────────────────────────         ──────────────────────           ────────────
  job.py  ── writes ──▶  <video>/.edit-mo-to/job.json  ◀── reads ──  server.py  ◀── HTTP/SSE ──  pages
  wait.py ◀── reads ───  <video>/.edit-mo-to/inbox.jsonl ◀── appends ─ server.py  ◀── answers ──  pages
          (runs in the background; exits when the editor answers, which wakes Claude)
```

One writer per file:

| File (in `<video folder>/.edit-mo-to/`) | Written by | Holds |
|---|---|---|
| `job.json` | Claude, only through `gui/job.py` | job card, step states, the open gate, step outputs (or paths to them), activity log |
| `inbox.jsonl` | the GUI server only (append) | the editor's answers, approvals, edits, comments and messages, one event per line, numbered |
| `gui.json` | the GUI server only | GUI-only state: comment drafts, last page, view choices |

**Edits made in the GUI** (a script cell, a shot's prompt or visual direction, approving a shot, ticking cuts, a change request) are inbox events, not direct writes. Claude applies them to the real files (script file, `storyboard.json`, cuts) through the normal tools, so every workflow file keeps one writer. Until Claude has applied an edit, the GUI shows it as **pending** on that field or card (the editor's text, with a "pending" chip); once `job.json` or the file shows it applied, the chip goes. If Claude rewrites a shot that has a pending edit, Claude applies the editor's edit on top and says so in the activity log. Comments and drafts are GUI-only data (`gui.json`) and are also sent as events so Claude sees them. *(Builder check: the designer's call.)*

**What the server runs by itself:** only read-only checks: reading `job.json`, reports and media for display, the setup check, whether files exist (keyframes saved from outside, clips in the folder), the CapCut-running check, and `capcut_project.py segments` / `list` for the Export banner. Every button that changes files or runs a workflow tool ("Check clips", "Apply selected cuts", builds, fixes, captions, music, the learning step) becomes an inbox event that Claude acts on; while Claude isn't listening, such a button shows "Saved, waiting for Claude". *(Builder check: the designer's call.)*

Uploaded files are copied into the video folder (references to `refs/`, keyframes to `storyboard/`, VO and music files to folders the step names). Large outputs stay where the workflow already puts them (`{tmp}/reports/<job>/…`, `storyboard/storyboard.json`, `storyboard.html`); `job.json` points to them by path and the server reads them for display.

### `gui/job.py` (Claude's side)

A small CLI so Claude never hand-edits JSON, with commands along the lines of:

- `job.py init <video folder> --client … --product …` (creates `.edit-mo-to/` and `job.json`)
- `job.py card <folder> key=value …` (job card fields: style, language, TEMP_EN state, VO, generator, timelines, project name…)
- `job.py step <folder> <step> <state>` (`pending | working | waiting | done | skipped | error`, with a short note)
- `job.py gate <folder> <step> --file gate.json` (opens a gate: its questions, the answer type per question, and its options) / `job.py close-gate …`
- `job.py output <folder> <step> <kind> <path>` (checklist, script table, timings, cuts, prompts, QA results, clip QC, change list…)
- `job.py log <folder> "<line>"` (activity feed)

It validates against a schema and refuses bad input, so a typo in a call fails loudly instead of breaking the page. Exact command names and the schema are the builder's (see "Left to the builder").

### How Claude and the GUI talk

- **At a gate:** Claude writes the gate with `job.py gate`, then runs `gui/wait.py <folder> --after <last event number>` **in the background**. `wait.py` blocks until the inbox has a newer event, prints those events, and exits. A finished background command wakes Claude in Claude Code, so Claude reads the answer and carries on. No polling by Claude, nothing for the editor to type in chat.
- **Listening status:** while `wait.py` runs it keeps a small `listening` file (pid, time, step) next to `job.json`. The GUI shows "Claude is listening · <step>" only while that process is alive; otherwise it shows "Claude isn't listening. Your message is saved; it's picked up when Claude next checks, or type 'go' in chat." Nothing the editor sends is lost: it stays in the inbox, and Claude reads every unread event when it next reaches `wait.py` or the start of a step.
- **Chat still works.** If the editor answers in chat instead, Claude takes that answer, closes the gate in `job.json` and stops the stale `wait.py`. Gate answers from either place are treated the same.
- **Messages without a gate.** The text boxes can be used at any time. A message sent while Claude is working on something else is read when Claude next checks the inbox (between agent runs and at each step start).
- **Long work** (agent runs, build, QA, timing, renders) is shown as `working` from `job.py step … working`, and becomes `done` or `error` only after the tool has returned and Claude has checked its result.

### Permission allowlist (Joshua's call)

A gate answered in the GUI only carries on by itself if Claude Code does not stop to ask permission before running `job.py`, `wait.py`, the server and the workflow tools. Each such prompt appears in the chat pane, and the GUI would stall with no sign of why. So edit-mo-to ships a **project allowlist** in `{root}/.claude/settings.json`, which pre-approves running only the workflow's own scripts: `.claude/edit-mo-to/gui/*.py` and `.claude/edit-mo-to/tools/*.py`, run with the tools `.venv` Python. Nothing broader: no general shell, no deletes, no git, no network commands.

- It ships to every editor with "update edit-mo-to" (`git pull`), so `.gitignore` must re-include it (`!/.claude/settings.json`; today `/.claude/*` ignores it). Each editor's own `.claude/settings.local.json` stays ignored and untouched.
- The tool commands contain machine-specific absolute paths (`{python}`, `{root}`), so the rules must be written so they match on every editor's machine, on Windows and on macOS, without listing anyone's paths. How (for example, running the tools with paths relative to `{root}`, or one small launcher with a fixed relative name) is the builder's call, but the result must be tested on a fresh checkout: a gate answered in the GUI runs through with no permission prompt.
- If a prompt still appears (a command outside the allowlist), the GUI shows "Claude needs your OK in chat" while the job is waiting, rather than looking stuck.
- The README says, in plain words, what the allowlist lets Claude run without asking.

### Launching

- `/edit-mo-to` (and `/practice-muna`) starts by making sure the GUI runs: if `http://127.0.0.1:<port>/api/ping` answers, reuse it; otherwise start `gui/server.py` in the background. Then open it: in Claude Code desktop, in the built-in browser pane (one tab, reused); elsewhere, the system browser. The page opens on the job being worked on, or on the dashboard when no job is known yet.
- Port: a fixed default (for example 4810), overridable as `gui_port` in `machine.json`; if it is taken by something that is not our server, say so and use the next free one.
- The server can also be started by hand (a one-line command in the README) to browse the dashboard without a session.

### Security, kept light

No login screen (the spec's wish), but the server must not be usable by other websites the editor visits: it binds to `127.0.0.1` only, prints a URL with a random per-launch token that it then keeps in a cookie, refuses API calls without it or with a foreign `Origin`, and only reads or writes files inside `{root}` and `{tmp}`.

## The app

### Look

- Dark creative-studio look, **Obsidian Champagne** colours (chosen from 9 options):
  `--bg #0C0B0A`, `--panel #151311`, `--panel2 #1D1A17`, `--line #2A2622`, `--line2 #3A342D`, `--text #F3EFE8`, `--muted #A69D91`, `--dim #6F675D`, `--accent #D4AF6A` (champagne gold), `--on-accent #1A1408`; status colours `ok #7DCB9C`, `wait #93B5E3`, `err #EE7B6E`, `optional #BBA6E0`, each with a 12% "soft" background. Text contrast at least 4.5:1; status is never shown by colour alone (every chip has a word).
- Fonts: Space Grotesk (headings), Inter (text), JetBrains Mono (paths, times, prompts), served from the repo so the app works offline, with system fallbacks.
- **Branding:** the sidebar header shows a gold **"JC" emblem**, "Edit Mo To" and "by Joshua Calonge". No other name appears anywhere, and there is no setting for one.
- **Verse:** the bottom of the sidebar, on every page, shows in a muted italic serif: *"Remember the Lord your God, for it is he who gives you the ability to produce wealth."* with "DEUTERONOMY 8:18" in small gold capitals.
- Step states in the sidebar: done (✓, green), working (blue), waiting on you (gold, "You" tag), optional (dashed, violet), error (red), not started (grey).

### Working ahead (Joshua's call, 2026-10-28)

The editor may work on steps that don't depend on earlier ones before Claude reaches them. A not-started step shows **"Open now"** in the sidebar when it takes early input, otherwise **"Waits for: <previous step>"**.

| Step | What the editor can do early |
|---|---|
| Brief | everything on the page (any time) |
| Script | paste their own script |
| Voiceover | upload the VO file(s) |
| B-roll & prompts | answer B-roll source and generator |
| Clips | set the clips folder |
| Captions | choose who adds captions |
| Music | choose the source, upload their own track |

Everything else waits. The table lives in one place, `gui/jobstate.py` (`EARLY`), and the server sends it with the job so the pages and the skill read the same list.

- An early input is an inbox event with `"early": true` and `gate: null` (an `answer` with `target` `<step>:<question id>`, or an `upload`). It is saved like any other event and shows on its page as **"Saved for later"**.
- When Claude reaches that step, it reads the step's early events and **confirms them instead of asking again**: the step's ⛔ gate still opens in its usual place and order, with the early answer as the default (a `confirm` question, "You chose X earlier. Still right?"). Nothing skips a gate; the editor only answers faster.
- An early answer never changes a step's state; only Claude moves a step out of "not started".

### Layout

Three columns: the sidebar (brand, Dashboard, Settings, the current video's 12 steps, the verse, the connection status), the page, and a right panel with the **job card** (the same fields as the skill's running card, including the TEMP_EN line), Claude's activity, the listening status, and a **"Tell Claude anything" text box for the whole job**. Below about 1100 px wide the right panel folds away behind a button.

Every step page has the same shape: what the step needs, Claude's output, the gate bar when the step waits on the editor ("Waiting on you: …" with the buttons), and at the bottom a **"Tell Claude about this step"** text box with that step's earlier messages and Claude's replies above it. A step-box message goes with that step's answers; a right-panel message is for the job as a whole.

Gates and questions are on the pages, not in pop-ups. Dialogs are only for confirmations, blocking warnings and close-up views (listed below).

### Pages

| Page | Skill step | What's on it | Gate on the page |
|---|---|---|---|
| Dashboard | — | a card per video folder (client, style, language, current step, what waits on the editor, progress), recent activity, the setup check, "New video". A video folder is any direct subfolder of `{root}`, except names starting with `.` or `_`, `docs` and `PYNK_AI_UGC_Studio`; folders without `.edit-mo-to/` show as "started before the GUI". Practice jobs (`{root}/_practice/<name>/`) show in their own "Practice" section *(builder check: the designer's call, matching the folders in `{root}` today)* | — |
| Settings & setup | — | the `machine.json` paths with found / missing per path, Save; checks for Python, ffmpeg/ffprobe, CapCut drafts folder, the CapCut MCP set-up; **Report a bug / Suggest an improvement** (see below) | — |
| Brief | 1–2 | brief link (Notion/URL), paste box, **one** "Additional instructions" box, reference file drop (copied to `refs/`), the picked style and script language, the brief checklist (rule, source, status), Claude's questions about the brief (up to 6) each with its own answer box | ⛔ confirm the checklist and style |
| Script | 3 | "Use my script" or "Write one", the editable script table (with the "English (temporary)" column when TEMP_EN is on), the "Storyboard first?" choice | ⛔ script approval (when Claude wrote it); ⛔ storyboard first? |
| Storyboard | 3 (optional) | see "Storyboard" below | ⛔ character sheet saved; ⛔ approve the direction |
| Voiceover | 4 | VO file drop, one file or one per hook/body, "Reuse an older VO" (dialog), the script language and the `--lang` it means | ⛔ VO file; ⛔ older-VO spans |
| Timing & cleanup | 5 | the line timings table with every `matched: false` line highlighted (Keep / Re-record); for talking-head A-roll, the cuts table (`id`, type, cut, removes, keeps, recommend) with a checkbox per cut and "Apply selected cuts" | ⛔ unmatched lines; ⛔ which cuts |
| B-roll & prompts | 6 | B-roll source and generator as buttons (marked "already answered" when the storyboard step asked them), the prompts per timeline as rows with Copy buttons and the full prompt on expand, QA results | ⛔ source; ⛔ generator |
| Clips | 7 | clips folder, "Check clips" (`qc_clips.py`), a row per expected clip (PASS / FLAG / missing); FLAG rows open the contact sheet; missing rows have Copy prompt | ⛔ regenerate real failures |
| Build & QA | 7–8 | build status, the `qa_check` and `qa` PASS / FAIL / OPEN table per timeline, "Ask Claude to fix" on a FAIL, the CapCut banner when a write is coming | ⛔ project name taken (dialog) |
| Review | 9 | the CapCut banner once per round, the change list (change, timeline, in place / new timeline, status), "Send changes", "I'm happy, go to captions", the editor's own edits found by `edit_diff` | ⛔ which timeline; ⛔ in place or new; ⛔ quit CapCut |
| Captions | 10 | the two choices side by side: "I'll run CapCut auto-caption" (then "Auto-caption is done") or "Claude adds them" (timelines, then Add captions), the TEMP_EN reminder | ⛔ who adds captions; timelines; quit CapCut |
| Music | 11 | Suno prompt from Claude (parts of max 18 s, Copy, crossfade notes) or the editor's own track, the music file drop, which timelines | ⛔ source; ⛔ timelines; quit CapCut |
| Export | 12 | the red "Delete the TEMP_EN_delete_me track before export" banner while any timeline still has it (from a fresh `capcut_project.py segments` check, naming the timelines), the brief's export settings, "I've exported, run the learning step" | — (the editor's) |

Steps the editor does outside the app (generate images, clips, VO, music; review in CapCut; export) carry a "You" tag and say what to do and where to put the file.

### Report a bug / Suggest an improvement (Settings)

Joshua asked for a place in Settings where editors report bugs and suggest improvements to the workflow.

- A **Bug / Suggestion** switch, a title field, and a text box ("What happened, or what would make the workflow better?"), with an optional "which step" picker.
- **Save** keeps it on this computer, one JSON line per report in `{root}/.claude/edit-mo-to/feedback.jsonl` (untracked, listed under the box with its date), so nothing is lost and Claude can read it ("look at my feedback").
- **Send to Joshua** opens a pre-filled new issue on `github.com/jushuaaang/edit-mo-to` in the system browser, with the title, the text, the type as a label word, and plain facts: edit-mo-to version (git short commit), Windows or macOS, the step picked. The editor reads it and submits it there themselves (a GitHub account is needed; nothing is sent automatically). Client names, file paths and job data are never added; only what the editor typed.
- *(Destination is the designer's proposal; confirm with Joshua at the plan review.)*

### Storyboard

The reason for the board is to copy each shot's prompt, so the board comes first and the images fill in.

- **Skeleton first.** After the script, the style agent (`mode: storyboard`, phase `prompts`) writes `storyboard/storyboard.json` with one beat per shot: number, script line (and the English line when TEMP_EN is on), estimated time, shot type (client clip or AI), visual direction and the **keyframe prompt**. The GUI shows it at once as a **grid** of cards; no images yet.
- **Character sheets on top.** For character ads (always Pixar and claymation; any ad with a recurring person or mascot) the first cards are the character sheet prompts, one per recurring character (`CHAR-1`, `CHAR-2`…). The shot cards show their shot info at once, but their keyframe prompts are **written only after every character sheet is saved**, by a second style-agent dispatch with the sheets attached as references, as the skill does today; until then the cards say "prompt comes after the character sheet". For other ads every shot's prompt is written in the first dispatch. *(Builder check: answered in the conversation.)*
- **Each card:** shot number, status chip (prompt ready, image added, changed, comment open, approved), script line, time, shot type, the prompt with **Copy prompt**, Comment. Clicking the image opens the **shot detail** dialog: big image slot, editable visual direction and prompt, comments, Choose file, previous / next shot, Request change, Approve shot.
- **Images drop in.** Dragging an image on a card saves it as `storyboard/SB-n.png` (or `CHAR-1.png`); saving a file with that name from outside also works (the page notices it). Replacing an image never changes the description or the prompt. `storyboard.py` already picks keyframes up by these names.
- **Filters:** All, Needs image, Changed, Comments. Grid is the main view; the detail dialog is the close-up.
- **Comments** per shot and a notes box for the whole board. When the editor requests changes, Claude rewrites only those shots and they are marked "changed".
- **Approval:** **Approve all** approves every shot at once, and single shots can be approved one by one. Approve all is always available; when AI shots still have no keyframe, an inline line says "3 shots have no keyframe yet (SB-5, SB-6, SB-8). Approve anyway?" with "Approve anyway" and "Wait for images".
- **Share page:** the existing self-contained `storyboard.html` (images embedded, safe to send a client) is still made from the same `storyboard.json`, linked as "Open share page".
- An approved storyboard carries into step 6 exactly as today (its shots and graphics carry over, the keyframes become the AI clips' start frames).

### Dialogs

New video (client, product, folder with a found / will-be-created check, optional brief link) · Shot detail · CapCut is still running (rechecks every 2 s; "I quit it, check again" / "Cancel this change") · Project name already taken (suggests "<Product> 2"; never overwrites) · Contact sheet (a flagged clip's frames; Use anyway / Copy prompt / Mark for regenerate) · Reuse an older VO (transcribe, tick sentences, assign timelines) · Change in place? (shows where the backup goes; or make a new timeline) · Learning step (each proposed preference with Save / Decline, and whether it is a general rule or a client note).

### CapCut safety in the GUI

When the next action writes to a CapCut project, the page shows a red banner ("Quit CapCut completely before Claude writes", with the reason) and a "CapCut is closed" button, once per review round as the skill says. The server checks for a running CapCut the same way `capcut_project.py` does (`_capcut_running`, reused, not copied); if it still runs, the "CapCut is still running" dialog shows. The tools keep refusing on their own, so the GUI only makes the rule visible.

`_capcut_running` only knows Windows today (`tasklist`); on a Mac it always reports "closed", so neither the tools nor the GUI would catch a running CapCut there. The build extends it for macOS (for example `pgrep -x CapCut`), with a test, so the tools and the GUI share one check that works on both. *(Builder check: the designer's call; it fixes an existing gap the anti-goals depend on.)*

## Changes to the existing workflow

- **SKILL.md / steps.md:** before step 1, start or reuse the GUI and create the job (`job.py init`); at each step keep `job.json` current (`job.py step`, `card`, `output`, `log`); at each ⛔ gate also open it in the GUI (`job.py gate`) and wait with `wait.py` in the background, accepting the answer from the GUI or the chat; read unread inbox events at each step start, including the step's early inputs (see "Working ahead"), and turn those into a confirmation at the step's gate. The gate wording stays.
- **Storyboard order** (`SKILL.md` step 3, `style-agent-contract.md` "Output: mode: storyboard", the style agents' storyboard sections): phase `prompts` also writes the skeleton `storyboard.json` (with a `prompt` field per beat and the character sheet beat), so the board exists before the images. Phase `board` then refines it from the saved images as today. The rule "never build the board before the images exist" becomes "never ask for approval of the direction as final while keyframes are missing, unless the editor chooses Approve anyway".
- **`storyboard.py`:** accept the new per-beat `prompt` (and a `status`) without changing its output for old files; keep rendering a shot card where no keyframe exists.
- **Deliverables in chat:** in this version Claude still shows the tables and prompts in chat exactly as today (the `CLAUDE.md` rule), and the GUI shows the same data from the files. This keeps the chat a full fallback. Whether to slim the chat output once the GUI is trusted is a later decision for Joshua.
- **`/practice-muna`:** gets the GUI the same way, so a new editor learns the app in the practice run.
- **README:** a line in "Step 1 · Install" and in the technical section on how the GUI opens and how to start it by hand. The install prompt itself stays.
- **`machine.example.json`:** document the optional `gui_port`.
- **`.claude/settings.json` and `.gitignore`:** the project allowlist above, and the `.gitignore` line that tracks it.
- **`capcut_project.py`:** `_capcut_running` learns macOS (see "CapCut safety in the GUI").

## Generator: Higgsfield replaces Seedance (Joshua's call, 2026-10-28)

AI clips are generated on **Higgsfield** or **Google Flow**; Seedance is no longer a generator choice. Higgsfield hosts several video models and Joshua picks the model per job, so the generator question becomes two answers: the site (`higgsfield` | `google-flow`) and, for Higgsfield, the **model**.

- **One rules table, in one file:** `.claude/edit-mo-to/generators.json` (tracked) holds, per generator and per Higgsfield model: label, clip length range (`min_s`, `max_s`, or fixed `lengths_s`), max attachments, whether a start frame is supported and how the prompt points at it (e.g. Seedance's "Start on @Image1."), whether an end frame is supported, and a `verified` date or `null`. Today's Seedance rules become the Higgsfield "Seedance" model rows; Google Flow's rules move there unchanged. `plan_tools.py` (prompt checks and rendering), `context_pack.py`, the style agents and the GUI read this file instead of hard-coding generator rules.
- **Unknown or unverified model:** Claude uses conservative rules (the strictest length and attachment limits in the table, a plain "Start from the attached image." line) and says so in chat and in the GUI, rather than guessing. The editor can correct a model's row in `generators.json`.
- **Gate:** step 6's generator question becomes "Where will you generate: Higgsfield or Google Flow?" (`generator`: `higgsfield` | `google-flow`) followed, for Higgsfield, by "Which Higgsfield model?" (`generator_model`, a choice from the table plus "Other"). The job card shows "Higgsfield · <model>". The storyboard step asks the same pair when it asks the generator early. Old jobs whose card says `seedance` are read as Higgsfield · Seedance.
- **Google Flow asks the model too (Joshua's ask, 2026-10-28).** Google Flow gets `models` like Higgsfield (e.g. Veo 3.1 Fast, Veo 3.1 Quality, Veo 3.1 Lite; secondary sources say Fast and Lite make 4, 6 or 8 s clips and Quality 8 s; all `verified: null`), and the same `generator_model` question follows "Google Flow": "Which Google Flow model?" with the table's models plus "Other". A Flow job with no model, and every old Flow job, keeps today's Flow rules (4–8 s, up to 7 attachments) and byte-identical prompts. The card shows "Google Flow · <model>".
- **Models Claude avoids, per editor (Joshua: Veo can be shown, but when Claude does the generating for him it must not use Veo).** Every model stays visible and choosable by the editor. Settings adds, per computer in prefs: "When Claude picks the model, never use" (checkboxes over `generators.json` models, `avoid_models`: `<site>:<model>` ids, known ids only) and "Claude's default model" (`default_model`). Whenever Claude chooses a model itself (generating on the editor's behalf, or proposing a default in the model question), it skips avoided models and uses the default; the model question still lists every model, with the default pre-selected. On Joshua's computer: avoid the Veo 3.1 rows (Google Flow and Higgsfield), default Google Flow · Gemini Omni Flash.
- **Gemini Omni Flash (Joshua's ask, 2026-10-28):** a Google Flow model row "Gemini Omni Flash" (`gemini-omni-flash`, aliases `omni flash`, `omniflash`), `verified: null` until Joshua confirms its limits.
- **Flagged prompts (Joshua: "sometimes I get flagged").** Video sites block some prompts with a vague reason and still use credits (reported for Omni Flash).
  - **Safer wording from the start:** the style agents follow a short "safe wording" list in `style-agent-contract.md`: no real or famous people's names, no famous characters or other brands' logos, no children unless the brief needs them, neutral body words (no "skin", "bikini", "undress", "body" as the subject; describe the action instead), no medical or "cure" claims, no blood, weapons or violence, and never a real person's photo as a start frame unless it is the client's own talent. `plan_tools.py check` warns (not errors) on listed risky words in a prompt, with a plain hint.
  - **"Got flagged" button** on every prompt row and storyboard card: sends an `action` event (`target "<step>:<prompt id>:flagged"`, optional note "what the site said"). Claude rewrites only that prompt in safer words (same shot, same timing), shows the old and new prompt, marks it "rewritten after a flag", and adds the trigger to the learning step so the editor can save it as a rule.
  - The risky-word list lives in one tracked file (`.claude/edit-mo-to/safe-words.json`), read by `plan_tools` and shown to the agents, so editors can extend it.

- **Preferences:** the shared `preferences.md` "Seedance" section becomes "Higgsfield · Seedance". An editor's own `my-preferences.md` is never edited by the build; a "Seedance" section there applies to the Seedance model on Higgsfield.

## Beginner friendly (Joshua's picks, 2026-10-28)

Editors using this are beginners. Every word the app shows is plain and short.

- **No codes in what the editor reads.** The app says "Shot 5", "the character sheet", "the question", never "SB-5", "CHAR-1" or "g-3". Files on disk keep their short names (`storyboard/SB-5.png`); only the words on screen change.
- **"What to do now" line** at the top of every page and on each dashboard card: one sentence saying whose turn it is and the next action ("Your turn: make the pictures for Shot 5 and Shot 6 in Higgsfield, then drop them on their cards." / "Claude is writing the prompts. Nothing to do yet."). Built from the job's real state (open question, step states, missing files, listening), never guessed.
- **Plain explanations of words.** A small ⓘ next to TEMP_EN, A-roll, B-roll, keyframe, timeline, VO, voiceover, question/gate and times like `2:12` ("2 seconds and 12 frames"). One short line each, on hover or tap, from one word list in the app.
- **Tell me when Claude needs me.** When a new question opens: a browser notification (asked once, can be turned off in Settings), a soft sound (can be turned off), and the tab title shows a count, e.g. "(1) Edit Mo To".
- **"Try a practice video"** on the dashboard: explains in one line what `/practice-muna` is, with a **"Start practice"** button (Joshua's call, 2026-10-28) that opens a new, visible Claude window in `{root}` already running `/practice-muna`: macOS opens Terminal (`osascript`, `tell application "Terminal" to do script` with `cd` to `{root}` and `claude "/practice-muna"`, the path safely quoted), Windows opens a command window (`start` + `cmd /k`, `cd /d`). `POST /api/practice` (token required) takes no arguments: the command and folder are fixed in the server, never built from the request. If the `claude` command is not found or the launch fails, the card says so in plain words and shows the Copy button instead. This is the one exception to "the GUI never starts Claude": it starts the editor's own Claude, in a window they see, only on their click; it never runs Claude hidden or with an API key.
- **"Why this step" and a time guess** under each step title: one plain line on why the step exists and roughly how long it takes (e.g. Timing: "Claude matches your voiceover to the script so cuts land on the words. About 1 minute."). Text lives in one place in the app, not copied from the skill.
- **Language: English or Taglish.** A switch in Settings changes every word the app shows to Taglish (plain, everyday Filipino-English, as editors talk). The editor's own text, Claude's messages and the script are never translated. All app words live in one word list per language so nothing is missed; Joshua checks the Taglish wording before it ships.
- **Auto-detect (Joshua's ask).** Claude, not the app, detects the editor's language from what the editor writes (chat and the app's message boxes): Taglish or Tagalog → Claude sets the app to Taglish (`job.py card ui_lang=tl`, a per-computer setting the server keeps), English → back to English. Claude's own chat replies always follow the editor's language (a skill rule). A language picked by hand in Settings wins and turns auto-detect off until set back to "Auto". Never translated: the script and VO (they follow the brief), generator prompts (stay English), the editor's own text.
- **Token usage (Joshua's ask).** The app shows how many tokens each video used ("about 1.2 million tokens so far", split into Claude and the helpers) and, on the dashboard, today's and this week's totals with the heaviest videos. Source: Claude Code's own session logs under `~/.claude/projects/<the {root} project folder>/` (the main `*.jsonl` and the helpers' logs), summing each message's `usage` (input, cache write, cache read, output) inside the time the job was active (`job.json` created to done; overlapping jobs share the time and are shown as "about"). The server reads **only the numbers and timestamps** from those files, never the conversation text, and only for the `{root}` project folder; this is the one read-only exception to "reads only inside {root} and {tmp}". Plan limits are not in any file, so the app shows a hint: "To see your plan limit, type /usage in Claude." If the logs are missing or their format changes, the app says "Usage not available" instead of guessing.
- **Usage read automatically (Joshua's ask: "the button does it all").** Claude Code passes the plan's usage to the status line command on stdin (`rate_limits.seven_day.used_percentage` / `resets_at`, `rate_limits.five_hour.used_percentage` / `resets_at`; Pro and Max plans, after the session's first reply; each window may be absent). edit-mo-to ships a project status line in `{root}/.claude/settings.json` (`"statusLine": {"type": "command", "command": ".claude/edit-mo-to/run gui/statusline.py"}`) that prints a short line (e.g. `Week 41% · Now 23% · resets Fri 9 AM`) and saves those numbers with the time to `{tmp}/gui/usage.json` (atomic write, fast, never fails the status line). The **"Update my usage"** button and a slow dashboard refresh read that file and show: week % used with its reset time, the 5-hour % ("right now"), "A video uses about N% of your week" (from the week % saved at each job's start and finish, finished jobs only, "Not enough videos yet to guess" until 3 are done) and "About N more videos this week" = (100 − week %) ÷ % per video, rounded down, never below 0, always "about". When the file is missing, old (over 30 minutes) or has no `rate_limits`, the box says plainly what to do ("Open Claude in the Video Editing folder and send one message, then press Update") and offers the manual box below as a fallback. The README says the project status line replaces an editor's own status line inside `{root}` only. The token counts from the logs stay as "Details".
- **Manual fallback (only when the automatic numbers are missing).** Claude also shows plan use on its `/usage` screen; the app never uses the editor's Claude login to fetch it. So:
  - The dashboard has one clear **"Update my usage"** button (Joshua's ask). It opens a small box with two steps: "1. In Claude, type `/usage`" with a Copy button, and "2. Type the weekly % you see" with a number field (0–100) and Save. When the last reading is over a day old or the week has reset, the button is highlighted (accent colour plus the word "old": "Update my usage (old)"). The editor types the weekly percentage `/usage` shows (e.g. 40). Each reading is saved with its time in the per-computer prefs.
  - From two or more readings and the token counts between them (from the logs above), the app learns about how many tokens make 1% of the editor's week. With that it shows, always with "about": "About 47% of your week used (last checked: 40% at 10:00 AM)", "A video uses about 6% of your week" (average of finished videos, "Not enough videos yet to guess" until 3 are done), and "About 8 more videos this week" = (100 − estimated %) ÷ % per video, rounded down, never below 0.
  - It asks for a fresh reading when the last one is over a day old, or when the estimate passes 100% or drops (the week reset), and then starts the estimate again from the new reading.
  - Token numbers stay in a "Details" fold for whoever wants them. The "/usage" hint is always shown next to the estimate.

## Generate for me (Joshua only, 2026-10-28)

Joshua sometimes has Claude make the media for him. This adds **"Generate for me"** buttons, on his computer only. It is an exception to the non-goal "generating clips, voiceovers, images or music stays the editor's", for an editor who turns it on.

- **Only where turned on.** `machine.json` (untracked, per computer) gets `"generate_for_me": true` on Joshua's Mac. Without it, no button, no setting and no skill text about it shows. Other editors never see it.
- **Buttons:** "Generate picture" on each storyboard card and the character sheet card; "Generate clip" on each clip row; "Generate voiceover" on the Voiceover page. Each sends an `action` event (`target "generate:<step>:<id>"`). The GUI never generates anything itself: Claude does it in the session, and the page shows "Claude is generating Shot 5…" only from Claude's real step and log state.
- **Pictures and clips with Joshua's Google Flow credits, through Claude in Chrome** (the browser extension he already uses with Claude Code): Claude opens Google Flow in his own visible Chrome window, picks the model (never one in his `avoid_models`; default Gemini Omni Flash), pastes the prompt, adds the start picture for clips, generates, downloads, and saves the file where the workflow expects it (`storyboard/SB-n.png`, the clips folder, by the existing names), then runs the usual checks (keyframe picked up; `qc_clips` for clips). Rules: only on his click; one item per click, never batches or loops; he can stop it anytime in the browser; a first-time warning he accepts once ("Google's terms may not allow automated use of Flow; this could flag your account"), stored in prefs; if Flow flags the prompt, Claude reports it and offers the "Got flagged" rewrite, never retries by itself.
- **Voiceover through the official ElevenLabs API** with Joshua's own key: a new tool `tools/elevenlabs_vo.py` (standard library only) takes the script file and a voice, shows the character count and estimated credits before it runs, and writes the result into `vo/`. Then the normal Timing step runs. The voice id and model are per-computer prefs, chosen once in Settings.
- **Keys stay private.** The ElevenLabs key lives only in `.claude/edit-mo-to/secrets.json` on his Mac (git-ignored, with a test that it is ignored), which he fills in himself. The key is never shown in the app, never sent to the page, never printed in chat or logs; Settings only shows "ElevenLabs key: set" or "not set".
- **Skill:** a short "Generate for me" section in SKILL.md, read only when `generate_for_me` is on, with the Chrome steps for Flow and the ElevenLabs call, and the rule that gates still apply (a generated file is confirmed at its step's gate like any other).

## Decisions that differ from the spec

- No `/edit-na-tayo`; only `/edit-mo-to` (and `/practice-muna`) open the GUI.
- No separate "Specific Instructions" box (agrees with the spec); one "Additional instructions" box on the Brief page.
- Text boxes: one per step page **and** one in the right panel for the whole job (Joshua's call).
- The storyboard "add clips" idea was dropped; the text boxes cover it.
- The architecture is fixed as the companion GUI (the spec left it open "after inspecting the repository").
- The spec's sections after 6 were never received; anything they held is not in this design.

## Left to the builder

- The exact `job.json` / `inbox.jsonl` schema and `job.py` command names (the fields named in this design must be covered).
- Server structure (standard-library `http.server` with server-sent events or short polling for live updates), file layout under `gui/`, and how static files are served.
- Upload limits and allowed types (at least PDF, DOCX, images, MP4/MOV, MP3/WAV; unsupported types refused with a clear message); streaming large video uploads to disk.
- How the page notices files saved from outside (polling the folder is fine).
- Tests: pytest for `job.py`, `wait.py` and the server API next to the existing tests in `tools/tests/`; a manual run of one practice job through the GUI on Windows, and on a Mac if one is available.
- Visual details within the look above (spacing, icons as SVG, motion that respects reduced-motion).

## Reference

A clickable mockup of every page and dialog was reviewed with Joshua on 2026-10-27 (session scratchpad, not kept in the repo). This document is the source of truth.
