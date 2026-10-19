# edit-mo-to: learning step (end of every video)

The goal: next time, the agents work more like the editor without being told again. Learn from what they **said** and from what they **did** in CapCut.

1. Collect evidence from this video:
   - every correction or change request the editor made (review loop, prompt fixes, script edits), quoted;
   - generation failures they reported and what fixed them;
   - brief rules that were new to us;
   - **their hand edits in CapCut.** For each timeline we built, run
     `edit_diff.py diff "<video folder>\.edit-mo-to\built\<timeline>.json" "<project>" "<timeline>" "<client folder>" --log "{root}/.claude/edit-mo-to/edit-patterns.jsonl" --video "<client> <video>"`.
     It lists what they trimmed, moved, deleted, added, re-scaled, re-timed or made louder or quieter, and turns that into patterns ("Shortened 6 of 9 b-roll clips by 0:12 on average", "Moved 3 overlay items onto a video cut", "Made music quieter by 4 dB"). `recurring` lists patterns seen in 2+ videos: the strongest rule candidates. Captions they added are counted, never learned from.
2. Turn the evidence into one-line rules, each tagged with the client and date, e.g. `- B-roll: no back-to-back clips of the same person [Zapply 2026-10-15]`.
   - A hand-edit pattern becomes a rule when it is recurring, or clear and repeated within this video. Write it as what to do next time ("B-roll cuts about 0:12 shorter than the VO span"), not as what happened.
   - **General or style rules** go in `{root}/.claude/edit-mo-to/my-preferences.md` (this editor's own rules, local only), in the right section. If it doesn't exist yet, create it with the same section headings as `preferences.md`. Never edit `preferences.md` (the shared starter rules) in the learning step.
   - **Client-only rules** go in `clients\<client>.md` (create it if new: product, talent, offer, claims, references, folder paths). Client notes stay on this computer only; the repo is public, so never put client names, links or briefs anywhere else in `.claude/` except as short tags. A style block worth reusing goes in `style-blocks.md` with the client details replaced by `[placeholders]`.
   - **Lasting changes to how an agent works** (a new required prompt block, a new layout) also go in `my-preferences.md`, under that style's section; agents read it after their own file. Don't edit `.claude/agents/` in the learning step: those files are shared, and editing them would clash with updates.
   - **Keep preferences lean:** merge a new rule into an existing one that says nearly the same thing, and replace rules it makes outdated (with the editor's OK), so the file doesn't grow every video.
3. ⛔ Show the proposed additions as a table, `# | File | Add/Change | Why (quote or hand-edit evidence)`, and ask: "Save these so I work like this next time?" Apply only what the editor approves.
4. Never delete an editor's rule without asking. If a new rule contradicts an old one, show both and ask.
5. **Nothing is uploaded.** The editor's rules, client notes and the hand-edit log stay on this computer (all gitignored). Never commit or push them. To use them on another computer, the editor copies `my-preferences.md`, `clients/` and `edit-patterns.jsonl` over.
6. Offer to delete the temp files in `{tmp}/build` and `{tmp}/qa` (ask first).
