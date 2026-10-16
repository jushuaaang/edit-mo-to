# D:\Video Editing

- The main workflow here is **/edit-mo-to**: client brief → script → VO → prompts/B-roll → CapCut build → review → captions (user) → music → export (user). Use it for any new client video.
- Learned preferences: `.claude\edit-mo-to\preferences.md`. Client notes: `.claude\edit-mo-to\clients\`. Read them before working on a client video.
- Deliverables (clip lists, prompts, edit plans) go **in chat as tables**, not in .md files. Times are in `seconds:frames` (30 fps). Use full file paths. Projects default to 9:16.
- The user adds captions (CapCut auto-caption) and does the export. Never add captions.
- Animated on-screen graphics (badges, CTA, stats, callouts) are HyperFrames overlays: `.claude\edit-mo-to\tools\motion_render.py` + catalogue `.claude\edit-mo-to\motion\CATALOGUE.md`; new looks/templates via `.claude\agents\motion-designer.md`.
- Each client or video has its own folder under `D:\Video Editing\`. `PYNK_AI_UGC_Studio\` is the older prompt-only setup with `/ugc`. Don't auto-run `/ugc` here.
- Design doc: `docs\edit-mo-to-design.md`.
