---
name: edit-mo-to-app
description: The edit-mo-to client video workflow WITH the Edit Mo To app (the editor's browser companion: steps, questions, job card, previews). Use only when the user types /edit-mo-to-app, or when the app's Start / Resume opened this session. For the chat-only workflow use /edit-mo-to.
disable-model-invocation: true
---

# /edit-mo-to-app

Run the `/edit-mo-to` workflow in **app mode**: read `{root}/.claude/skills/edit-mo-to/SKILL.md` and its `reference/steps.md`, and follow them exactly, app parts included (that skill's "Two modes": open the app with `launch.py --open`, keep the job with `job.py`, open every ⛔ stop as a gate in the app and wait with `wait.py`, send every reply to the app with `job.py say`). Everything else (the 12 steps, the stops, the agents, the tools) is that skill's.
