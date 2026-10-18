# edit-mo-to: learned preferences

The user's corrections and approvals from past sessions. Every agent reads **General** plus its own sections. The learning step adds rules here only after the user OKs them.
Session tags: Cirelle fe9a0790 · GODA 6ec28f49 · Nuva 73daf057 · Nativia ac6ec8ea · Muslin-UGC 71ae1a3e · Muslin-clay 8e760cdc · Strapless d835d69e · Zapply 4971109a · NorthPower 3e72f5fc · Shoe 3420882a · ExchangeLife 095da884 · design 2026-10-15 (this workflow).

## General
- **Follow the client brief to the letter.** Every rule in it is tracked and checked. [design]
- **Step by step:** stop at every gate until the user says proceed. [Nativia]
- **Deliverables go in chat as tables, never in a .md file** [Strapless, Nuva, NorthPower]. Prompts must be easy to copy, with the look written into the prompt [Nuva].
- **Timecodes are `seconds:frames`** at 30 fps (`1:29` = 1s 29f); past 60s, `m:ss:ff`. Never decimals; they confused the user [ExchangeLife, Strapless].
- **Full file paths and names**, including the full folder address [Zapply, ExchangeLife].
- **Map every clip to its script line** [Muslin-clay, Zapply].
- **Never reuse a clip**, hooks included [Zapply, Strapless].
- **Engaging and varied:** near-identical shots are "too boring". Every shot is a different angle [Strapless, ExchangeLife, Shoe].
- **Default 9:16**, 1080×1920, 30 fps project [design]. Generated clips can be 24 fps, so watch frame counts [Strapless].
- **Never add captions**; the user does them with CapCut auto-caption. All on-screen text goes in during the edit, never in the generation [design].
- **Save credits:** efficient clip lengths, and suggest stock or internet clips where they'd do [GODA, Nativia].
- **Explain creative choices** in 2–3 lines when a deliverable needs it [NorthPower, Nuva].
- **A talking-head mash-up is several different creators** reading the same script, cut line by line between them. One person's batch isn't a mash-up [ExchangeLife 2026-10-16].
- **Playbook client clips may be downloaded** into the video's `clips\` folder. Say what and how big first [ExchangeLife 2026-10-16].
- **Brief hook instructions are literal.** For "founder traveling in Brazil and smiling to the camera", scan the whole client library for exactly that and confirm a real smile into the lens in frame 1. Close enough doesn't count [ExchangeLife 2026-10-16].

## Prompts (all generators)
- **Timing is exact to the VO.** Clip length = the VO span it covers. Dialogue is quoted verbatim in per-second windows ("0.0–2.5s: … speaking: '…'") plus "Her mouth movement matches this pacing exactly." Batch the words per word or per idea [Cirelle, GODA, Muslin-clay, design].
- **Repeat the locks in every prompt** (the user always had to ask for them again):
  - **Master realism line** (live footage) [Nativia]: "Shot on an iPhone, vertical 9:16, natural iPhone HDR, slight handheld shake, light natural background blur with the room still readable, real room tone. [Wardrobe line.] Skin keeps its true [tone], real pore texture, never plastic. No text, captions, graphics, filters, or logos anywhere. The phone and any hand holding the camera are never visible."
  - **Product lock** [Cirelle]: "The [product] is @ImageN and it stays exactly as @ImageN shows it in every frame." Labels are "an exact copy of its own attached product photo". State the form factor ("pouch, never a bottle"). Never describe the product visually; reference the image [ugc skill, NorthPower].
  - **No text:** "No subtitles, no captions, no on-screen text… The spoken line is audio only." Subtitles were a repeated failure [Cirelle].
  - **Voice lock:** "the same voice in every clip", naming each character's voice tone [Cirelle, Muslin-clay].
  - **Look lock:** "Her skin tone, freckle level, hair color, and the overall color grade never change"; "never becomes blurry, soft, or smeared", even when the start frame is soft [Cirelle].
  - **Pacing:** "starts speaking in the very first moment… no long pauses, no dead air… clip ends mid-motion" [Cirelle].
  - **Style bible** for stylised work, pasted in full at the end of every prompt [NorthPower].
- **Attachments:** an "Attach:" line in order, numbered @Image1… [Nativia].
- **Ultra-realistic iPhone look:** don't blur the background (UGC) [Nativia, GODA]; steady camera for talking heads [Cirelle]; the iPhone is never visible, even in a mirror [Nuva].
- **Detailed prompts** [Zapply, Shoe].
- **B-roll / gap-fill prompt shape:** Subject · Setting · Action (second ranges) · Camera · Look · Negative. Graphics prompts: Format · Scene · Subject · Motion timeline · Camera · Lighting · Avoid [Strapless, Zapply].

## Google Flow
- Model: Omni Flash. Modes: Ingredients to Video, or Frames to Video (start + end frame). Ingredients reinterprets the scene, so when continuity matters use **Frames to Video**, and make "the video start and end exactly as I attach the start and end image" [Cirelle].
- **Max 7 attachments** [Nativia].
- **Clip length 4–8s**; pick the most efficient [Nativia]. If Omni Flash only offers fixed lengths (e.g. 10s), take the next one up and trim in the edit [Muslin-clay].
- **Image first, then video from that image**, to save credits [Shoe, Muslin-clay].
- **Animation and graphics shots are generated in Flow too** [Nativia].
- Audio attachment is unconfirmed. If Flow won't take the VO, lay it over in the edit and fix lip-sync there [Muslin-clay, Nativia].

## Seedance
- Used for Pixar-style work (2.5) with @Image/@Video tags. Prompts start "Start on @Image1" (the keyframe) [NorthPower].
- Minimum clip is about 4–5s, so short beats are generated long and trimmed. Continue from the previous clip by attaching it as @Video1 [NorthPower].

## UGC
- **Structure:** several hooks (variants) + body + CTA. Body first, then hooks, one at a time [Nativia].
  - **Timeline 01 = hook 1 + body + CTA; Timelines 02+ are hook only** (hook A-roll, B-roll, graphics). The user pastes T01's body into them [Fascora 2026-10-17].
- **Host A-roll:** lip-synced to the ElevenLabs VO, 4–8s clips, cut on VO pauses. B-roll covers the VO between host shots [Nativia].
- **Long talking-head:** about 36 clips, chained so each clip's last frame is the next one's start frame [Cirelle].
- **Body B-rolls:** no reference image, a different person in each, not looking at camera, 4s each [GODA].
- **Generate reference images first:** headshot, full body, setting, before/after [Nativia, ugc skill].
- **Wardrobe line in every live clip** (the host once rendered with no shirt) [Nativia].
- **Lip-sync:** drift of 8+ frames (0.27s) is visible. First retime the clip in CapCut ("slow to 92%"); for big mismatches, regenerate with a word-matched prompt [Nativia, lipsync_report.md].

## B-roll
- **Mostly the client's B-roll.** Generate AI only where nothing fits or AI is clearly better, and always ask first. Clients may want both [Zapply, design].
- **Cut length follows the line's mood:** fast beats about 1.5–2s, calmer or explanatory lines can hold 6–8s. A guide, not a limit [rehearsal 2026-10-15]. Only a max stated in the client brief is law (Zapply: 4s max) [Zapply].
- **The product is always centred in every B-roll shot.** Set scale and position per cut, check the in, mid and out frames against a ±10% centre box, and swap the shot if the product drifts. Talking heads stay framed as shot [ExchangeLife 2026-10-16].
- **End on product B-roll,** not a talking face, so the CTA's last line plays over the product [ExchangeLife 2026-10-16].
- **Finding replacement shots:** stop at the first ones that fit and differ from what's in the edit; don't scan the whole library for better ones [ExchangeLife 2026-10-16].
- **With a reference video, match its cut rhythm:** cut per word or idea (about 1–1.5s), not one clip per line; about 15–20 shots per 20s of VO [ExchangeLife 2026-10-16].
- **Show the exact cut** per clip: source in–out in `seconds:frames` [Zapply, Strapless].
- **Tables** include line, VO time, full path, cut, length, and a Slot (FULL / TOP / BOTTOM) for splits; layout in `style-agent-contract.md` [Strapless, Zapply].
- **Split screens:** before/after 50/50 vertical, BEFORE on top, 1080×960 panes, 6px white divider, labels. AI macro or graphic on top, live footage below. 2×2 or 3×3 grids for social proof [Strapless, Zapply].
- **Cataloguing client folders:** ffprobe for duration and fps; ffmpeg frame strips or contact sheets for content. Watch for rotation metadata on phone clips [Strapless].
- **AI B-roll morphs or goes smooth after about 2s,** so keep those cuts short [Strapless].
- **No talking-head stretch over about 5s without B-roll.** Keep a short emotional beat (2–3s) on the face, then cover the rest with B-roll mapped to the words [Fascora 2026-10-17].
- **Graphic B-roll** matches the client's AI library style (e.g. "premium dark-tech", navy with electric-blue glow), with the key subject in the centre 1080×960 band so it crops cleanly into a split [Zapply].

## Claymation
- Google Flow: image prompt first, then video prompt. **Fit the lines in the time** [Muslin-clay].
- **Style and audio block in every clip,** in full, with each character's voice tone so voices never change (see `clients/muslin-cotton.md`) [Muslin-clay].
- **One speaker at a time;** the other keeps its mouth closed (overlapping mouths failed). Keep characters in the same setting [Muslin-clay].
- **Named characters show their names** in two-character B-roll. Calendars show real numbers. A sleeping person has eyes closed, so drop "big stylized eyes" there [Muslin-clay].
- **B-roll matches the reference video** and says which line it goes over [Muslin-clay].

## Pixar
- **Hook, body, CTA,** told like a Pixar story, relatable to everyone. Offer several story options for the user to pick [NorthPower].
- **Keyframes S1–Sn, then clips C1–Cn** (Seedance), 30–45s total, generated at 5s and used at 2.5–8s [NorthPower].
- **Style bible at the end of every prompt.** No faces or eyes on objects or props; only characters get "big expressive eyes" [NorthPower].
- **Story details read clearly** (shirt buttons visible: no tie). Moods match the beat (happy after the product). Hero/product backgrounds suit the audience (masculine, not pastel). Background particles move [NorthPower].
- **Suno music** comes in 18s max: split into parts and crossfade. Duck music 6–8 dB under VO. Mark SFX hit points [NorthPower].
- **Edit-stage text** (the user does captions): seal or badge plus an animated SHOP NOW button on the CTA [NorthPower].

## Product ad
- **10–20s, 2–4s clips, every clip a different angle,** following the inspiration videos. Logo in one clip; overlay the real logo file if the generated one warps [Shoe].
- **One-word descriptor per shot** (Refined, Commanding, Timeless). No claims the brand hasn't verified [Shoe].
- **Image first, then video** from it. Each video prompt ends "One continuous shot, no cuts, no text." [Shoe]
- **TikTok product ads have no script,** cut to music: cuts on the beat, best clips in the first 5s, the first clip grabs attention within 1s [design, ExchangeLife].
- **Congruency:** clips from the same batch (lighting, setting, outfit, nails). Each clip starts after the action begins and ends before it stops [ExchangeLife].

## Editing in CapCut
- **On-screen graphics are HyperFrames motion overlays** (badges, CTA buttons, end cards, stats, callouts, word pops, hook numbers): transparent `.mov` files rendered by the editor during the build, on top tracks; CapCut keeps their alpha. New looks and templates come from `motion-designer`; small tweaks are done directly with the user. Templates: `.claude\edit-mo-to\motion\templates\` [design 2026-10-16].
- **"Talking head + Apple UI" style** (approved on the Cirelle v2 rehearsal) [Cirelle 2026-10-16]:
  - **Titles:** two-line heavy-italic keyword titles at chest height (`kinetic-title`). White top line; the bottom line's colour changes per phrase (blue / yellow / green / pink). Pop in with a small shake.
  - **Pop-ups:** iOS glass cards beside the hands or product, never over the face (`glass-card`, `glass-split`, `glass-compare`).
  - **Glass cards use `glass-card-v2`:** real frosted glass the footage shows through, one bold title and one sub big enough for 50+ viewers, line icons in brand colours, no emoji or glossy app-icon squares, rendered natively for the canvas (never upscaled), no orphan words ("make it beautiful not ai slop") [Fascora 2026-10-17].
  - **Flashes:** full-frame colour flashes on beats (`color-flash`): blue at the open, white on a turn, green on the payoff.
  - **Zooms:** punch-ins (1.12–1.2) on true emphasis words only, about one every 10–15s, cut at word gaps, never on two A-roll shots in a row; everything else stays at base framing [Fascora 2026-10-17].
  - **Hooks get a denser motion edit:** a glass title whose key phrase lights up on its spoken word, plus what fits (a "6 months ago │ Now" toggle, a counter for numbers, a pain marker on the problem area, light sweeps on cuts at about half brightness). Never over the face, never doubling the captions [Fascora 2026-10-17].
  - **Captions:** the keyword titles replace CapCut auto-captions in this style; don't double them.
  - **Sound design:** whoosh on each flash and title, pop on each card, ping on ✓ and the payoff (`"sfx": "default"` on every overlay), under her voice [2026-10-16].
  - **Reference:** `C:\Users\Keytech\Downloads\Talking Head (Short-form) with Devin jatho's + Apple UI stlyle. #videoediting  #talkinghead #editor.mp4` (Windows PC).
- **Reference videos teach effects, not looks.** Adapt a reference's editing effects and motion, but choose colours and fonts fresh for each video, matched to the client's brand, the brief and the mood; never copy the reference's palette or type ("you dont need to follow the color… even the fonts") [2026-10-19].
- **Clean timelines:** overlays (cards, counters, titles) and their SFX start on a video cut, never at arbitrary times between cuts. In Fascora T02–T04 the user re-placed them by hand [Fascora 2026-10-18].
- **Import first, then edit.** Files the user hands over (generated clips, B-roll, VO, music) are imported into the project's media panel under their real names, and the timeline uses those files, not hidden copies [2026-10-16].
- **The user's CapCut is 9.6.** The editor agent builds projects. Hooks and revisions go on separate timelines [design].
- **Mirroring is manual** (the tools can't flip clips): list the clips to mirror. Check each clip's flags and tag text and mirror only those that read backwards (Exchange Life trial batch: all; Advanced batch: only IMG_1225) [ExchangeLife, ExchangeLife 2026-10-16].
- **Speed changes for lip-sync:** list them per clip [Nativia].
- **Stills get a slow zoom** of about 1s [GODA].
- **The user exports**, usually 1080p, 60 fps if the brief asks [ExchangeLife].

## Known generation failures (prevent in prompts)
- **Label text drifts or garbles:** label lock + attach the real photo [Cirelle, Nativia].
- **Subtitles appear:** "no subtitles" line [Cirelle].
- **Grade, skin tone or hair colour shifts between clips:** look lock [Cirelle].
- **Blurry or soft clips:** sharpness line [Cirelle].
- **Mispronounced brand words:** spell them phonetically ("RAY-sih-mik") [Cirelle, Nativia].
- **Lip-sync drift:** see UGC [Nativia].
- **Missing wardrobe:** wardrobe line [Nativia].
- **Props or products change shape:** "stays exactly as @ImageN" [Nativia].
- **Rotations morph text:** keep products square to the lens [Cirelle].
- **Similar characters swap identities:** one character per shot, or state it explicitly [Muslin-clay].
- **Faces on objects:** "no eyes, no faces" line [NorthPower].
- **Continuity breaks** (glasses off then on, a pillow moving by itself): continuity lock in every prompt (props that leave stay gone, nothing in the room moves on its own, nothing appears or disappears); lock the camera when the room matters, or use Frames to Video from the clip's own first frame [Fascora 2026-10-17].
- **A phone in frame** (stand, counter, mirror): "no phone anywhere in frame", not only "the filming phone is never visible" [Fascora 2026-10-17].
- **Secondary people read too young:** for 50+ briefs write them clearly 55+ (grey hair, wrinkles, crow's feet), or keep their face out of frame [Fascora 2026-10-17].
