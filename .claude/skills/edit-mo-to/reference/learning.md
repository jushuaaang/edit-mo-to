# edit-mo-to: learning step (end of every video)

The goal: next time, the agents work more like the user without being told again.

1. Collect evidence from this video:
   - every correction or change request the user made (review loop, prompt fixes, script edits), quoted;
   - generation failures they reported and what fixed them;
   - manual work they did in CapCut that we could have done or pre-planned;
   - brief rules that were new to us.
2. Turn the evidence into one-line rules, each tagged with the client and date, e.g. `- B-roll: no back-to-back clips of the same person [Zapply 2026-10-15]`.
   - **General or style rules** go in `{root}/.claude/edit-mo-to/preferences.md`, in the right section.
   - **Client-only rules** go in `clients\<client>.md` (create it if new: product, talent, offer, claims, references, folder paths).
   - **Lasting changes to how an agent works** (a new required prompt block, a new layout) go in `{root}/.claude/agents/<style>.md`. Keep edits small and in that file's own style.
3. ⛔ Show the proposed additions as a table, `# | File | Add/Change | Why (quote)`, and ask: "Save these so I work like this next time?" Apply only what the user approves.
4. Never delete a user rule without asking. If a new rule contradicts an old one, show both and ask.
5. **Sync to GitHub** (repo `https://github.com/jushuaaang/edit-mo-to`, private). After the approved changes are saved, commit only the workflow files: `git -C "{root}" add -A`, then commit with a one-line summary of what was learned, then push. `.gitignore` keeps client footage out. Never force-push. If the push is rejected because the other PC pushed first, `git pull --rebase` and push again, and ask the user if there's a conflict.
6. Offer to delete the temp files in `{tmp}/build` and `{tmp}/qa` (ask first).
