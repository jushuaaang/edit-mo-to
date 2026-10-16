# edit-mo-to: learned preferences

What the user (the editor) has asked for, corrected or accepted in past sessions. Every agent reads **General** plus its own section. The learning step at the end of each video adds to this file, but only after the user OKs it.
Session tags: Cirelle fe9a0790 · GODA 6ec28f49 · Nuva 73daf057 · Nativia ac6ec8ea · Muslin-UGC 71ae1a3e · Muslin-clay 8e760cdc · Strapless d835d69e · Zapply 4971109a · NorthPower 3e72f5fc · Shoe 3420882a · ExchangeLife 095da884 · design 2026-10-15 (this workflow).

## General
- **Follow the client brief to the letter.** Every rule in it is tracked and checked. [design]
- **Work step by step.** "you will not proceed until I say proceed." Stop at every gate. [Nativia]
- **Deliverables go in chat, never in a .md file.** "dont make an md, list it here" [Strapless]; "do not write in md file. post it here" [Nuva]; "put it here not in the md file" [NorthPower].
- **Use tables.** "give it in table format" [Strapless]. Prompts must be easy to copy ("include the look in the prompt so it is easy to copy") [Nuva].
- **Timecodes are `seconds:frames`**, e.g. `1:29` = 1s 29f at 30 fps. Past 60s it's min:sec:frames. The user was confused by decimals [ExchangeLife, Strapless].
- **Give full file paths and full file names**, including the full folder address [Zapply, ExchangeLife].
- **Map every clip to its script line** ("include in what line I will put it") [Muslin-clay, Zapply].
- **Never reuse a clip**, hooks included ("do not reuse clips for hook") [Zapply, Strapless].
- **Make it engaging and varied:** "make it engaging to watch" [Strapless]; "all almost identical... too boring" [ExchangeLife]. Every shot is a different angle [Shoe].
- **Default ratio is 9:16**, 1080×1920, 30 fps project [design]. Generated clips can be 24 fps, so watch frame counts [Strapless].
- **Captions are done by the user** with CapCut auto-caption, so never add them [design]. All on-screen text goes in during the edit, never in the generation.
- **Save credits.** Pick efficient clip lengths and suggest stock or internet clips where they would do ("dont just have generated vids, to save credits") [GODA, Nativia].
- **Explain the creative choices** in 2–3 lines when a deliverable needs it [NorthPower, Nuva].
- **A talking-head mash-up means several different creators.** Find a folder where multiple creators read the same script, then cut line by line between them. One person's batch isn't a mash-up ("it must be mash up since that's what the brief says") [ExchangeLife 2026-10-16].
- **Client clips on Playbook may be downloaded directly** into the video's `clips\` folder. Say what and how big first ("Yes, you download it") [ExchangeLife 2026-10-16].
- **Brief hook instructions are literal.** If the brief says "founder traveling in Brazil and smiling to the camera", scan the whole client library for exactly that and confirm a real smile into the lens in frame 1. A close-enough clip doesn't count ("change the hook also. you forgot this one Hook clip") [ExchangeLife 2026-10-16].

## Prompts (all generators)
- **Timing is exact to the voiceover.** Clip length = the VO span it covers. Dialogue is quoted verbatim with per-second windows ("0.0–2.5s: … speaking: '…'") and "Her mouth movement matches this pacing exactly." Batch the words by word or by idea ("fix the seconds and word batching in evry prmopts"; "the prompt must be either per word or per idea") [Cirelle, GODA, Muslin-clay, design].
- **Repeat the locks in every prompt.** The user always asked to add them again:
  - **Master realism line**, live footage ("always add the master realism line") [Nativia]. Accepted form: "Shot on an iPhone, vertical 9:16, natural iPhone HDR, slight handheld shake, light natural background blur with the room still readable, real room tone. [Wardrobe line.] Skin keeps its true [tone], real pore texture, never plastic. No text, captions, graphics, filters, or logos anywhere. The phone and any hand holding the camera are never visible."
  - **Product lock** ("always add the product lock") [Cirelle]: "The [product] is @ImageN and it stays exactly as @ImageN shows it in every frame." Labels are "an exact copy of its own attached product photo". State the form factor ("pouch, never a bottle"). Never describe the product visually; reference the image instead [ugc skill, NorthPower].
  - **No text:** "No subtitles, no captions, no on-screen text… The spoken line is audio only." Subtitles appearing was a repeated failure [Cirelle].
  - **Voice lock:** "the same voice in every clip". Name the voice tone per character [Cirelle, Muslin-clay].
  - **Look lock:** "Her skin tone, freckle level, hair color, and the overall color grade never change"; "never becomes blurry, soft, or smeared", even when the start frame is soft [Cirelle].
  - **Pacing:** "starts speaking in the very first moment… no long pauses, no dead air… clip ends mid-motion" [Cirelle].
  - **Style bible** for stylised work, pasted in full at the end of every prompt ("add the style bible at each prompt you will give") [NorthPower].
- **Attachments:** list them in order on an "Attach:" line, numbered @Image1… in that order [Nativia].
- **Ultra-realistic iPhone look:** "do not blur the background" (UGC) [Nativia, GODA]; "the camera must be steady" for talking heads [Cirelle]. The iPhone must never be visible in a mirror [Nuva].
- **Detailed prompts:** "please be detailed with the prompt" / "give the detailed prompt" [Zapply, Shoe].
- **Shape of a B-roll / gap-fill prompt:** Subject · Setting · Action (second ranges) · Camera · Look · Negative. Graphics prompts use Format · Scene · Subject · Motion timeline · Camera · Lighting · Avoid [Strapless, Zapply].

## Google Flow
- Model is Omni Flash. Modes: Ingredients to Video, or Frames to Video (start frame + end frame).
  - Ingredients mode reinterprets the scene. When continuity matters, use **Frames to Video**, and make "the video start and end exactly as I attach the start and end image" [Cirelle].
- **Max 7 attachments** [Nativia].
- **Clip length: 4s shortest, 8s longest.** Pick the most efficient length [Nativia]. Omni Flash may only offer fixed lengths (e.g. 10s); if so, pick the next length up and trim in the edit [Muslin-clay].
- **Image first, then video from that image**, for credit efficiency [Shoe, Muslin-clay].
- **Generate animation and graphics shots in Flow too** [Nativia].
- Audio attachment is unconfirmed. If Flow won't take the VO, lay the VO over in the edit and fix lip-sync there [Muslin-clay, Nativia].

## Seedance
- Used for Pixar-style work (2.5) with @Image/@Video tagging. Prompts start "Start on @Image1" (the keyframe) [NorthPower].
- Minimum clip is about 4–5s, so short beats are generated long and trimmed. A clip can continue from the previous one by attaching it as @Video1 [NorthPower].

## UGC
- **Structure:** hooks (several, as variants) + body + CTA. Body first, then hooks, one at a time [Nativia].
  - In CapCut, the body and CTA go on Timeline 01 and each hook gets its own timeline [design].
- **Host A-roll:** lip-synced to the ElevenLabs VO, clips 4–8s, cut points on VO pauses. B-roll covers the VO between host shots [Nativia].
- **Long talking-head:** about 36 clips, chained so each clip's last frame is the next clip's start frame [Cirelle].
- **Body B-rolls:** no reference image, a different person in each, no looking at camera when it's B-roll, 4s each [GODA].
- **Generate reference images first:** headshot, full body, setting, before/after [Nativia, ugc skill].
- **Wardrobe line goes in every live clip** (the host once rendered with no shirt) [Nativia].
- **Lip-sync:** drift of 8+ frames (0.27s) is visible. First fix is to retime the clip in CapCut ("slow to 92%"); for big mismatches, regenerate with a word-matched prompt [Nativia, lipsync_report.md].

## B-roll
- **Use the client's B-roll mostly.** Generate AI only where nothing fits or AI is clearly better, and always ask first. Clients may want both [Zapply, design].
- **Cut length follows the mood and context of the script.** Fast beats cut short (about 1.5–2s); calmer or explanatory lines can hold 6–8s. Pacing is a guide, not a hard limit [rehearsal 2026-10-15]. Only a max the client brief states is law (Zapply: "the b rolls must be 4 secs max") [Zapply].
- **The product is always in the centre of every B-roll shot.** Set scale and position per cut, check the in, mid and out frames with a ±10% centre box, and swap the shot if the product drifts. Talking heads stay framed as shot ("the product must always be at the center") [ExchangeLife 2026-10-16].
- **End on product B-roll,** not on a talking face, so the CTA's last line plays over the product ("put a broll on the ending") [ExchangeLife 2026-10-16].
- **When there's a reference video, match its cut rhythm.** Cut per word or idea (about 1–1.5s), not one clip per script line; about 15–20 shots per 20s of VO ("make it engaging and have fast cuts and more videos") [ExchangeLife 2026-10-16].
- **Show the exact cut** for each clip as source in–out in `seconds:frames` ("add also the timestamp where I will cut the video") [Zapply, Strapless].
- **Tables** always include the line, VO time, full path, cut and length, with a Slot (FULL / TOP / BOTTOM) for splits [Strapless, Zapply]. The exact layout is in `style-agent-contract.md`.
- **Split screens:** before/after splits are 50/50 vertical, BEFORE on top, panes 1080×960, with a 6px white divider and labels. AI macro or graphic on top, live footage below. Use 2×2 or 3×3 grids for social proof [Strapless, Zapply].
- **Cataloguing client folders:** ffprobe gives duration and fps; ffmpeg frame strips or contact sheets show content. Watch for phone clips with rotation metadata [Strapless].
- **AI B-roll morphs or goes smooth after about 2s,** so keep those cuts short [Strapless].
- **Graphic B-roll style** matches the client's AI library (e.g. "premium dark-tech", navy with electric-blue glow). Keep the key subject in the centre 1080×960 band so it crops cleanly into a split [Zapply].

## Claymation
- Google Flow, image prompt first, then video prompt. **Fit the lines in the time** [Muslin-clay].
- **Style and audio block in every clip,** with each character's voice tone written in so voices never change (quote it in full; see `clients/muslin-cotton.md`) [Muslin-clay].
- **One speaker at a time.** The other character keeps its mouth closed. Overlapping mouths was a failure. Keep characters in the same setting [Muslin-clay].
- **Named characters show their names** in two-character B-roll. Calendars show real numbers. A sleeping person has eyes closed, so drop "big stylized eyes" for those shots [Muslin-clay].
- **B-roll should match the reference video** and say which line it goes over [Muslin-clay].

## Pixar
- **Hook, body and CTA,** told like a Pixar story and relatable to everyone. Offer several story options and let the user pick [NorthPower].
- **Keyframes S1–Sn, then clips C1–Cn** (Seedance), 30–45s total. Generated at 5s and used at 2.5–8s [NorthPower].
- **Style bible at the end of every prompt.** No faces or eyes on objects or props; only characters get "big expressive eyes" [NorthPower].
- **Story details must read clearly** (e.g. shirt buttons visible: no tie). Moods must match the beat (happy after the product). Hero/product backgrounds suit the target audience (masculine, not pastel). Background particles must move [NorthPower].
- **Music from Suno** comes in 18s max, so split it into parts and crossfade. Duck music 6–8 dB under VO. Mark SFX hit points [NorthPower].
- **Edit-stage text** (the user does captions): seal or badge plus an animated SHOP NOW button on the CTA [NorthPower].

## Product ad
- **10–20s, 2–4s clips, every clip a different angle,** following the inspiration videos. Include the logo in one clip, and overlay the real logo file if the generated one warps [Shoe].
- **One-word descriptor text** per shot (e.g. Refined, Commanding, Timeless). Skip claims the brand hasn't verified [Shoe].
- **Generate the image first, then the video** from it. End each video prompt with "One continuous shot, no cuts, no text." [Shoe]
- **TikTok product ads have no script** and are cut to music: cuts on the beat, best clips in the first 5s, the first clip grabs attention within 1s [design, ExchangeLife].
- **Congruency:** use clips from the same batch, matching lighting, setting, outfit and nails. Each clip starts after the action begins and ends before it stops [ExchangeLife].

## Editing in CapCut
- **On-screen graphics are HyperFrames motion overlays.** Badges, CTA buttons, end cards, stats, callouts, word pops and hook numbers are rendered as transparent `.mov` files by the editor during the build and placed on top tracks. New looks and templates come from the `motion-designer` agent; small overlay tweaks are done directly with the user. CapCut keeps their alpha. Templates: `.claude\edit-mo-to\motion\templates\` [design 2026-10-16].
- **"Talking head + Apple UI" style** (approved on the Cirelle v2 rehearsal) [Cirelle 2026-10-16]:
  - **Titles:** two-line heavy-italic keyword titles at chest height (`kinetic-title`). The top line is white; the bottom line takes a colour that changes per phrase (blue / yellow / green / pink). They pop in with a small shake.
  - **Pop-ups:** iOS glass cards beside the hands or the product, never over the face (`glass-card`, `glass-split`, `glass-compare`).
  - **Flashes:** full-frame colour flashes on beats (`color-flash`): blue at the open, white on a turn, green on the payoff.
  - **Zooms:** punch-ins (1.12–1.2) on key words, cut at word gaps.
  - **Captions:** the keyword titles replace CapCut auto-captions in this style, so don't double them.
  - **Sound design:** a whoosh on each flash and title, a pop on each card, a ping on ✓ and on the payoff (`"sfx": "default"` on every overlay), kept under her voice. Added 2026-10-16 from HyperFrames' bundled SFX library.
  - **Reference:** `C:\Users\Keytech\Downloads\Talking Head (Short-form) with Devin jatho's + Apple UI stlyle. #videoediting  #talkinghead #editor.mp4` (on the Windows PC).
- **Import first, then edit.** The files the user hands over (generated clips, B-roll, VO, music) are imported into the CapCut project so they show in its media panel under their real names, and the timeline uses those imported files, not hidden copies [2026-10-16].
- **The user's CapCut is 9.6.** Projects are built by the editor agent. Hooks and revisions go on separate timelines [design].
- **Mirroring is manual** (the tools can't flip clips), so list the clips to mirror. Check each clip's flags and tag text, and mirror only the ones that read backwards. In the Exchange Life trial batch every clip was mirrored, but in the Advanced batch only IMG_1225 was [ExchangeLife, ExchangeLife 2026-10-16].
- **Speed changes for lip-sync:** list them per clip [Nativia].
- **Stills get a slow zoom** of about 1s [GODA].
- **The user exports**, usually at 1080p, 60 fps if the brief asks [ExchangeLife].

## Known generation failures (prevent in prompts)
- **Product label text drifts or garbles:** use the label lock and attach the real photo [Cirelle, Nativia].
- **Subtitles appear:** add the "no subtitles" line [Cirelle].
- **Color grade, skin tone or hair color shifts between clips:** add the look lock [Cirelle].
- **Blurry or soft clips:** add the sharpness line [Cirelle].
- **Mispronounced brand words:** spell them phonetically ("RAY-sih-mik") [Cirelle, Nativia].
- **Lip-sync drift:** see UGC [Nativia].
- **Missing wardrobe:** add the wardrobe line [Nativia].
- **Props or products change shape:** use the "stays exactly as @ImageN" line [Nativia].
- **Rotations morph text:** keep products square to the lens [Cirelle].
- **Two similar characters swap identities:** put one character per shot, or state it explicitly [Muslin-clay].
- **Faces appear on objects:** add the "no eyes, no faces" line [NorthPower].
