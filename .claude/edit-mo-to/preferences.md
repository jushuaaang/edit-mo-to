# edit-mo-to: starter rules (shared)

Proven defaults that every editor starts with. Agents read **General** plus their own sections here, then the editor's own `my-preferences.md` (local, never uploaded): **where the two disagree, `my-preferences.md` wins.** The learning step never edits this file; it writes the editor's rules to `my-preferences.md`. Improve these starter rules only on purpose, in the repo.

## General
- **Follow the client brief to the letter.** Every rule in it is tracked and checked.
- **Step by step:** stop at every gate until the editor says go on.
- **Deliverables go in chat as tables, never in a .md file.** Prompts go in copyable code blocks, with the look written into the prompt.
- **Timecodes are `seconds:frames`** at 30 fps (`1:29` = 1 s 29 f); past 60 s, `m:ss:ff`. Never decimals.
- **Full file paths and names**, including the full folder.
- **Map every clip to its script line.**
- **Never reuse a clip**, hooks included.
- **Engaging and varied:** every shot a different angle; near-identical shots are boring.
- **Default 9:16**, 1080×1920, 30 fps project. Generated clips can be 24 fps, so watch frame counts.
- **Never add captions**; the editor does them with CapCut auto-caption. All on-screen text goes in during the edit, never in the generation.
- **Save credits:** efficient clip lengths; suggest stock or client clips where they'd do.
- **Explain creative choices** in 2–3 lines when a deliverable needs it.
- **Brief hook instructions are literal:** find exactly what the brief describes, not a close-enough shot.

## Prompts (all generators)
- **Timing is exact to the VO.** Clip length = the VO span it covers. Dialogue quoted verbatim in per-second windows ("0.0–2.5s: … speaking: '…'") plus "Her mouth movement matches this pacing exactly." Batch words per word or per idea.
- **Repeat the locks in every prompt**, in full, never "same as above":
  - **Realism line** (live footage): "Shot on an iPhone, vertical 9:16, natural iPhone HDR, slight handheld shake, light natural background blur with the room still readable, real room tone. [Wardrobe line.] Skin keeps its true [tone], real pore texture, never plastic. No text, captions, graphics, filters, or logos anywhere. The phone and any hand holding the camera are never visible."
  - **Product lock:** "The [product] is @ImageN and it stays exactly as @ImageN shows it in every frame." Labels are "an exact copy of its own attached product photo". State the form factor. Never describe the product visually; reference the image.
  - **No text:** "No subtitles, no captions, no on-screen text… The spoken line is audio only."
  - **Voice lock:** "the same voice in every clip", naming each character's voice tone.
  - **Look lock:** skin tone, hair colour and colour grade never change; the clip "never becomes blurry, soft, or smeared".
  - **Pacing:** "starts speaking in the very first moment… no long pauses, no dead air… clip ends mid-motion".
  - **Style bible** for stylised work, in full at the end of every prompt.
- **Attachments:** an "Attach:" line in order, numbered @Image1….
- **Detailed prompts.** B-roll / gap-fill shape: Subject · Setting · Action (second ranges) · Camera · Look · Negative. Graphics: Format · Scene · Subject · Motion timeline · Camera · Lighting · Avoid.

## Google Flow
- Modes: Ingredients to Video, or Frames to Video (start + end frame). When continuity matters, use Frames to Video.
- **Max 7 attachments. Clip length 4–8 s**; if only fixed lengths are offered, take the next one up and trim in the edit.
- **Image first, then video from that image**, to save credits.

## Seedance
- Prompts start "Start on @Image1" (the keyframe). Minimum clip about 4–5 s: generate long, trim in the edit. Continue a clip by attaching the previous one as @Video1.

## UGC
- **Structure:** several hooks (variants) + body + CTA. **Timeline 01 = hook 1 + body + CTA; each other hook gets its own hook-only timeline.**
- **Host A-roll:** lip-synced to the VO, cut on VO pauses. B-roll covers the VO between host shots. Generate host clips **long (8 s)** so one take covers a whole line, then cut it into pieces on speech pauses with UGC jump cuts. **Never fill a gap with a still or freeze frame**: it reads as lag.
- **Generate reference images first:** headshot, full body, setting.
- **Wardrobe line in every live clip.**
- **Lip-sync:** drift of 8+ frames is visible. Generators ignore the VO's pace, so time each host clip's own guide speech (whisper, in the VO's language), set `src_in` per jump-cut piece, and keep speed within 0.85–1.15×. Words that still drift go under B-roll, never a speed-up past 1.15×. Regenerate only for big mismatches.

## B-roll
- **Mostly the client's B-roll;** generate AI only where nothing fits, and ask first.
- **Cut length follows the line's mood:** fast beats about 1.5–2 s, calmer lines up to 6–8 s. Only a max stated in the brief is law.
- **The product sits in the centre of product shots;** talking heads stay framed as shot.
- **Show the exact cut** per clip (source in–out in `seconds:frames`), with a Slot (FULL / TOP / BOTTOM) for splits.
- **Split screens:** before/after 50/50, BEFORE on top, 1080×960 panes. 2×2 or 3×3 grids for social proof.
- **AI B-roll morphs after about 2 s,** so keep those cuts short.
- **No talking-head stretch over about 5 s without B-roll.**

## Claymation
- Image prompt first, then video prompt; fit the lines in the time.
- **Style and audio block in every clip,** with each character's voice tone.
- **One speaker at a time;** the other keeps its mouth closed.

## Pixar
- **Hook, body, CTA,** told like a short story; offer several story options.
- **Style bible at the end of every prompt.** No faces or eyes on objects; only characters get "big expressive eyes".
- **Music:** duck it 6–8 dB under the VO; mark SFX hit points.

## Product ad
- **10–20 s, 2–4 s clips, every clip a different angle,** cut on the beat; best clips in the first 5 s.
- **One-word descriptor per shot;** no claims the brand hasn't verified. Logo in one clip; overlay the real logo file if the generated one warps.
- **Congruency:** clips from the same batch (lighting, setting, outfit).

## Editing in CapCut
- **On-screen graphics are HyperFrames motion overlays** from `motion/CATALOGUE.md`, in the client's colours and fonts.
- **Reference videos teach effects, not looks:** adapt their editing effects and motion; choose colours and fonts fresh for each client and mood.
- **Clean timelines:** overlays and their SFX start on a video cut or a spoken word.
- **Transitions:** few and subtle: 3–5 of ≤0.3 s, only at section changes (hook → body, start of a benefit run, back to the host); every other cut stays straight. Each gets a short whoosh centred on the cut, under the VO. On an existing timeline, add them with `capcut_project.py patch` op `transition` (copies a CapCut effect by name from a past project whose effect is cached).
- **Zoom-ins for emphasis only,** never two in a row.
- **Import first, then edit:** the editor's files appear in the media panel under their real names.
- **Mirroring is manual:** list clips that read backwards.
- **The editor exports.**

## Known generation failures (prevent in prompts)
- **Label text drifts or garbles:** product lock + attach the real photo.
- **Subtitles appear:** the "no subtitles" line.
- **Grade, skin tone or hair colour shifts between clips:** look lock.
- **Mispronounced brand words:** spell them phonetically.
- **Props or products change shape:** "stays exactly as @ImageN".
- **Similar characters swap identities:** one character per shot.
- **Faces on objects:** the "no eyes, no faces" line.
- **Continuity breaks** (props reappear, things move by themselves): a continuity lock in every prompt.
- **A phone in frame:** "no phone anywhere in frame".
