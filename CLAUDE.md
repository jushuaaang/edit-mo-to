# Video Editing workflow (edit-mo-to)

- **Machine paths:** `{root}`, `{python}`, `{tmp}`, `{capcut_drafts}` and `{mcp_servers}` in these files mean the values in `.claude/edit-mo-to/machine.json` (print them with `python3 .claude/edit-mo-to/tools/machine.py`). `{root}` is this folder. If `machine.json` is missing, copy `machine.example.json` and fill it in. Use forward slashes; they work on Windows and Mac.

- The main workflow here is **/edit-mo-to**: client brief → script → VO → prompts/B-roll → CapCut build → review → captions (the editor chooses who) → music → export (user). Use it for any new client video.
- Preferences: `.claude/edit-mo-to/preferences.md` (shared starter rules) and `.claude/edit-mo-to/my-preferences.md` (this editor's own learned rules, local only; **wins on conflict**). Client notes: `.claude/edit-mo-to/clients/` (local only). Read them before working on a client video.
- Deliverables (clip lists, prompts, edit plans) go **in chat as tables**, not in .md files. Times are in `seconds:frames` (30 fps). Use full file paths. Projects default to 9:16.
- The user does the export. Never add captions before step 10, except the `TEMP_EN_delete_me` review track (temporary English lines for a script that is not English or Filipino; the user deletes it before export); at step 10 the editor chooses: they run CapCut auto-caption, or Claude adds simple text captions with the script's exact words.
- Animated on-screen graphics (badges, CTA, stats, callouts) are HyperFrames overlays: `.claude/edit-mo-to/tools/motion_render.py` + catalogue `.claude/edit-mo-to/motion/CATALOGUE.md`; new looks/templates via `.claude/agents/motion-designer.md`.
- Each client or video has its own folder under `{root}/`. `PYNK_AI_UGC_Studio/` is the older prompt-only setup with `/ugc`. Don't auto-run `/ugc` here.
- Design doc: `docs/edit-mo-to-design.md`.
- **Updates:** never pull or push on your own. When the editor says "update edit-mo-to", run `git -C "{root}" pull --ff-only` and report what changed. Never commit or push personal files (`my-preferences.md`, `clients/`, `edit-patterns.jsonl`, `_practice/`).
