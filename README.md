# edit-mo-to

Joshua's end-to-end client video workflow for Claude Code: client brief → script → voiceover → B-roll / AI prompts → CapCut project build (with HyperFrames motion overlays and sound design) → review → captions → music → export.

Open Claude Code in this folder and run **`/edit-mo-to`**.

This repo holds the **workflow only**: skills, agents, preferences, client notes, motion templates, SFX and tools. Client footage, CapCut projects and installed dependencies are never committed (see `.gitignore`).

## What's inside
| Path | What |
|---|---|
| `CLAUDE.md` | house rules Claude reads in this folder |
| `.claude/skills/edit-mo-to/` | the `/edit-mo-to` skill: 12 gated steps, plus step detail and the learning step |
| `.claude/agents/` | ugc, broll, claymation, pixar, product-ad (style), editor (CapCut builds), qa (checks), motion-designer (new looks and templates) |
| `.claude/edit-mo-to/preferences.md` | everything learned about how Joshua edits |
| `.claude/edit-mo-to/clients/` | per-client notes |
| `.claude/edit-mo-to/style-agent-contract.md` | edit-plan format shared by the agents |
| `.claude/edit-mo-to/motion/` | HyperFrames templates (14), `CATALOGUE.md`, `sfx/` (19 Pixabay-licence sounds), `sfx_defaults.json` |
| `.claude/edit-mo-to/tools/` | `capcut_project.py`, `media_timing.py`, `motion_render.py`, `plan_build.py`, `plan_preview.py` + tests |
| `.claude/edit-mo-to/setup/capcut-start.mjs` | launcher that auto-starts the CapCut backend for the MCP server |
| `docs/` | design doc and build plan |

## Setting up a new PC (Windows)

1. **Install:**
   - CapCut desktop (tested with 9.6);
   - Node.js 22+;
   - Python 3.12;
   - Git;
   - ffmpeg with ffprobe on PATH (`winget install Gyan.FFmpeg`);
   - Claude Code.
2. **Clone this repo as the workflow folder:**
   ```
   git clone <this repo> "D:\Video Editing"
   ```
   If the folder already holds client footage, run `git init`, `git remote add origin <url>` and `git pull origin main` inside it instead. `.gitignore` keeps the footage out.
3. **Tools (Python):**
   ```
   cd "D:\Video Editing\.claude\edit-mo-to\tools"
   python -m venv .venv
   .venv\Scripts\python -m pip install -r requirements.txt
   ```
4. **HyperFrames (Node, pinned 0.8.162):**
   ```
   cd "D:\Video Editing\.claude\edit-mo-to\motion"
   npm ci
   ```
5. **CapCut backend + MCP server**, in `%USERPROFILE%\mcp-servers`:
   ```
   git clone https://github.com/sun-guannan/VectCutAPI.git            (tested at 269a404)
   git clone https://github.com/MigueDuque/capcut-mcp-server-extended.git   (tested at a3aa1fd)
   cd VectCutAPI
   python -m venv .venv
   .venv\Scripts\python -m pip install -r requirements.txt
   copy config.json.example config.json
   cd ..\capcut-mcp-server-extended
   npm install
   copy "D:\Video Editing\.claude\edit-mo-to\setup\capcut-start.mjs" "%USERPROFILE%\mcp-servers\capcut-start.mjs"
   claude mcp add capcut --scope user -e CAPCUT_API_URL=http://localhost:9001 -- node "%USERPROFILE%\mcp-servers\capcut-start.mjs"
   ```
6. **Check:**
   ```
   cd "D:\Video Editing\.claude\edit-mo-to\tools"
   .venv\Scripts\python -m pytest tests -q
   ```
   The CapCut tests need the backend running on port 9001.

**Path note:** some files still name this PC's paths (`D:\Video Editing`, `C:\Users\Keytech\…`, CapCut's drafts folder under `%LOCALAPPDATA%`). On a PC with a different username or drive, update those paths (search for `Keytech`), or make the workflow portable with a single config file first.

## Keeping PCs in sync
Preferences, client notes and new templates change as the workflow learns.
- **Before starting a video:** `git pull`.
- **After the learning step:** commit and push.
