# edit-mo-to: starter rules (shared)

Proven defaults that every editor starts with. Agents read **General** plus their own sections here, then the editor's own `my-preferences.md` (local, never uploaded): **where the two disagree, `my-preferences.md` wins.** The learning step never edits this file; it writes the editor's rules to `my-preferences.md`. Improve these starter rules only on purpose, in the repo.

## General
- **Follow the client brief to the letter.** Every rule in it is tracked and checked.
- **Step by step:** stop at every gate until the editor says go on.
- **Deliverables go in chat as tables, never in a .md file.** **Every prompt goes on the job's prompt sheet** (storyboard, character sheet, keyframe, video; `tools/prompt_sheet.py`, published as an Artifact), one card each with Copy, with the look written into the prompt; never pasted in chat. Chat gets the table and the sheet link.
- **Storyboard order:** generate the images first (character sheet first for Pixar / character ads, then the storyboard keyframes), and build the whole storyboard only once the images are saved.
- **Timecodes are `seconds:frames`** at 30 fps (`1:29` = 1 s 29 f); past 60 s, `m:ss:ff`. Never decimals.
- **Full file paths and names**, including the full folder.
- **Map every clip to its script line.**
- **Never reuse a clip**, hooks included.
- **Engaging and varied:** every shot a different angle; near-identical shots are boring.
- **Default 9:16**, 1080×1920, 30 fps project. Generated clips can be 24 fps, so watch frame counts.
- **Never add captions before step 10,** except the `TEMP_EN_delete_me` review track (temporary English lines for a script that is not English or Filipino); at step 10 the editor chooses: CapCut auto-caption, or Claude's text captions (see Captions). All on-screen text goes in during the edit, never in the generation.
- **Always save credits** (every paid generator: Flow, Higgsfield, ElevenLabs). Re-read `my-preferences.md` right before generating, since rules get added mid-job. Clips go **x1 per prompt, never x2 or x4** (pictures may be x2: they cost no credits). Use the shortest clip length that covers the slot (4 s before 6 or 8 s) and no paid upscales. Reuse before regenerating: another take, the unused part of a take, or a trim. Regenerate only a shot that truly fails, one at a time at x1. Use free paths first (the image model for stills, edit an image instead of making a new video), and suggest stock or client clips where they'd do. Never raise outputs or length "for more choice"; say the credit cost when proposing a regeneration.
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

## Higgsfield · Seedance
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

## Drama
Characters act a scripted scene and speak their own lines (each clip's own voice, no separate VO). One agent, `drama`, with a **look**: `realistic` (live-action AI) or `cartoon` (2D cartoon / anime).

**Story and pacing (both looks)**
- **Script is law:** every line word for word, in order, by its character, names as the script has them. The reference gives pacing, layout and energy, never its shots: design your own staging.
- **Hook:** the first 2 s land on the conflict, a sharp reaction or the strongest line the script allows; never a slow open or logo. **Hook versions follow the brief:** make them only if the brief asks, the way it says; otherwise one hook. Never add words the client didn't write.
- **Arc:** setup → conflict → the product as the turning point or resolution, never a jarring interruption.
- **Pacing:** shots about 1.5–3 s; pauses over 0.3 s cut to ~0.15 s (~0.1 s before and ~0.15 s after each line); no dead air.
- **A visual change every 3–5 s** by angle, shot size or a listener reaction, **never a zoom or punch-in**. Jump cuts inside the same shot get a short soft Dissolve (~5 f).
- **J/L cuts by reaction overlays:** plan reaction clips of the listener (mouth closed, reacting to the line) and lay them muted over part of the speaker's line; the voice always comes from the speaker's own clip, so lips never drift.

**Framing and look (both looks)**
- **Shot progression:** wider shots at the setup, tighter close-ups as the tension rises; faces carry the emotion.
- **Eyes:** the speaker looks at the other character, never at the camera (only the CTA lines may look to camera). One speaker talking at a time; the others keep their mouth closed.
- **Location (strict):** one spot per scene; each character keeps their side of the frame and the same background behind them; a new location only when the script changes scene. Set lock in words + one approved establishing keyframe attached to later shots of that set.
- **Colour follows each scene's mood** (e.g. cooler and tenser in the conflict, warmer at the resolution): one grade per scene, natural skin tones.
- **Safe zones:** faces, key action and graphics inside the 9:16 centre safe area, clear of the right-side icons, the top tabs and the caption band.
- **Voice lock per character,** in full in every talking prompt: age, accent, pitch, tone, pace, attitude, so a regenerated take sounds like the same person.
- **Storyboard first:** keyframes approved by the editor before any clip is generated; clips x1; regenerate a bad take instead of fixing it in the edit.

**Sound and delivery (both looks)**
- Clear, forward dialogue at one level; light SFX for script actions and tension (room tone, risers, impacts, door, footsteps), never theatrical.
- **Music:** none until step 11; if the editor adds it there, low and ducked under the voices.
- Captions at step 10 as usual; a caption-free twin timeline only if the brief asks.
- Graphics (title card, offer, badge, end card) only when the brief, script or reference has them.

**Realistic look**
- **Both characters in every medium and wide shot** (change the angle, never drop the other person); nobody hidden behind props.
- **Close-ups:** true close-ups of the speaker looking off-camera at the other character; attach only that character's sheet plus their fixed background plate (cropped from the avatar or establishing frame).
- **No over-the-shoulder shots** with someone's back in the foreground.
- Clips play at 1.0x with their own audio and **no `audio_lead`** (Flow's own lip/voice pairing); never slow a flawed clip down.
- Ultra-realistic look per the brief; no text, logos or watermarks in frame.

**Cartoon look**
- **Layout (letterbox frame):** 9:16 canvas with a full-width picture panel (about 1080×885, top edge near y 620, lower than centre), a bold white two-line title hook above it (heavy sans, caps), and a dark textured background filling the rest. Clips are generated **16:9 landscape** and scaled to fill the panel height (sides cropped by the canvas); the frame (background with a transparent panel window) and the title sit on top tracks for the whole video.
- **Avatars:** the client's character sheets are attached to every shot of that character (Flow max 7 attachments); never redesign a character. One look per character per scene (hair, outfit).
- **Style:** match the reference's drawing style, not the sheets' style (style reference board + face and hair locks per character).
- Mix of wide, medium, close-up, extreme close-up and inserts of hands or props.

## Editing in CapCut
- **On-screen graphics are HyperFrames motion overlays** from `motion/CATALOGUE.md`, in the client's colours and fonts.
- **Overlays render slim and offline:** the build renders each unique overlay once, then re-encodes it to a slim ProRes 4444 `.mov` (about 40% smaller, same look, alpha kept). GSAP is bundled, so renders need no internet once HyperFrames has cached the fonts.
- **Reference videos teach effects, not looks:** adapt their editing effects and motion; choose colours and fonts fresh for each client and mood.
- **Clean timelines:** overlays and their SFX start on a video cut or a spoken word.
- **Transitions:** few and subtle: 3–5 of ≤0.3 s, only at section changes (hook → body, start of a benefit run, back to the host); every other cut stays straight. Each gets a short whoosh centred on the cut, under the VO. On an existing timeline, add them with `capcut_project.py patch` op `transition` (copies a CapCut effect by name from a past project whose effect is cached).
- **Zoom-ins for emphasis only,** never two in a row.
- **Import first, then edit:** the editor's files appear in the media panel under their real names.
- **Mirroring is manual:** list clips that read backwards.
- **Captions are step 10's choice:** the editor runs CapCut auto-caption, or Claude adds text captions on the reviewed timeline (look below). Until then the only text track Claude adds besides badges and CTAs is `TEMP_EN_delete_me`, which the editor deletes before export.
- **The editor exports.**

## Captions
Starter look for Claude's step-10 captions (`build_project.py captions`, text track `captions`). The plan's `captions_style` overrides any of it (VectCutAPI text keys, e.g. `{"font": "Poppins_Bold", "font_size": 12, "transform_y": -0.62}`).
- **Bold sans,** Poppins Bold (`Poppins_Bold`; it covers accents like á, ñ, ü), white, black stroke and a shadow, no box.
- **Bottom band:** inside the bottom `caption_band_px` (400 px), clear of faces and the product label.
- **2–4 words per chunk,** cut at punctuation and pauses first; no one-word orphan; a number stays with its unit.
- **Pop-in** on each chunk (short pop-up intro); no word-by-word animation. For an animated look, the editor uses CapCut's caption presets on auto-caption.
- **The script's exact words,** timed to the VO's word timings, never retyped by hand.

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
