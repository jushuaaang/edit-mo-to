# Motion overlay catalogue (HyperFrames → transparent 9:16 .mov)

Every template is `templates\<name>.html`. For exact variables and defaults, run `motion_render.py list`. Overlays are planned in the edit plan's `overlays`, rendered by the editor during the build (`motion_render.py render`), and placed on top tracks. CapCut 9.6 keeps their alpha.

## Classic
| Template | Use for | Key vars |
|---|---|---|
| badge | guarantee, offer, claim badge near the top | text, accent, bg, top |
| cta | animated SHOP NOW button with tap ripple | text, bg, bottom |
| end-card | closing panel: headline, sub, button | headline, sub, button, logo_text |
| stat | counting number with a label | value, prefix, suffix, label |
| word-pop | one big word slam with an underline | text, highlight, top |
| callout | dot + line + tag pointing at a product | text, x, y, side |
| hook-number | numbered hook badge (1, 2, 3…) | number, label |
| split-labels | BEFORE / AFTER labels + divider for split screens | top_label, bottom_label |
| mirror-molecules | 50/50 bar, then mirror pair, then winner (science reveal) | split_text, pair_text, payoff_text, t_pair, t_payoff |

## "Talking head + Apple UI" style (approved on Cirelle v2, 2026-10-16)
| Template | Use for | Key vars |
|---|---|---|
| kinetic-title | two-line heavy-italic keyword title (white + colour line); replaces captions in this style | line1, line2, accent, top |
| glass-card | iOS card with icon, title, sub, beside the hands or product | icon, icon_bg, title, sub, x, y, width |
| glass-split | segmented bar (R 50% │ S 50%) | left, right, left_value, right_value |
| glass-compare | ✓/✕ verdict rows, or mirror twins (`mode`) | win, lose, win_note, lose_note, mode, t_verdict |
| color-flash | full-frame colour wash on a beat | color, peak, hold, vignette |

## "Fascora glass" system: native 4:5, works for 9:16 too (built 2026-10-17)
Every template here has a `height` var (default 1350, use 1920 for 9:16) and a `scale` var. They render at the full canvas size, so place the .mov at CapCut scale 1.0, x 0, y 0, with position set by the template vars (canvas px). No emoji: icons are SVG line glyphs. Type is Inter with SF-style tracking. The material is a flat iOS frosted fill with a 1px inner edge and a soft two-layer shadow. Accents are the pouch blues (navy `#0e2f5a`, mid `#1f6fb8`, wave `#8fd3ff`).
| Template | Use for | Key vars |
|---|---|---|
| glass-card-v2 | premium iOS card: one bold title line + one short line. The title shrinks up to 15% to stay on one line, otherwise wraps balanced; never leaves an orphan word | title, sub, icon (check/plus/leaf/drop/clock/heart/none), accent, x, y, anchor, scale, max_width, theme |
| glass-title | hook title: light glass label (line 1) + navy panel (line 2); key phrase lights up in wave blue on its spoken word | line1, line2, key, t_key, y, align, scale, size1, size2 |
| glass-toggle | iOS segmented control, e.g. "6 months ago │ Now"; thumb springs across on the word | left, right, t_switch, y, scale |
| glass-counter | big counting number + label in a glass card ("20 clients a day") | value, prefix, suffix, label, from, t_count, count_dur, x, y, anchor |
| pain-marker | pulsing pain point on the body + leader line + glass tag | label, x, y, side, dx, dy, color |
| light-sweep | soft blue-white glint across a cut (0.5 s), a premium alternative to `color-flash` | tint, peak, angle, dir |

## Creator effects kit (effects adapted from a "7 effects" creator reel, 2026-10-19)
Effects and motion only. **Never copy a reference's colours or fonts:** every template takes `font` plus colour vars (`bg`, `fg`, `accent`, …), and the style agent sets them from the client's brand, the brief and the mood (e.g. Inter + navy for a 50+ health brand, a condensed display face for loud energy, a serif for luxury). Defaults are neutral placeholders. All are 9:16 at `height` 1920 (1350 for 4:5).
| Template | Use for | Key vars |
|---|---|---|
| section-chip | numbered section header: square number pops, label chip wipes open ("3 · ORBIT"); lists, steps, "N reasons" | number, label, x, y, bg, fg, font |
| big-text | huge 1–2 line words; line 1 drops in with motion blur, line 2 a beat later. **Text behind the speaker** when paired with `cutout` | line1, line2, t_line2, color, color2, shadow, y, size, font |
| checklist | card of steps that tick off on their spoken words | title, items (a\|b\|c), t_checks (s,s,s), x, y, width, bg, fg, accent |
| notify | phone notification banners: `stack` (pop in, alternate sides) or `rain` (fall tilted and pile up); results, reviews, orders, social proof | items (title\|body;…), mode, t_gap, y, app (play/bell/heart/chat), bg, fg, icon_bg |
| prompt-bar | a question or AI prompt typed into an input bar, then sent; "I asked…", search, app ads | text, cps, t_start, y, width, bg, fg, accent |
| title-card | hook title at the top or end card, with an optional comment-CTA chip (key word bold) | title, sub, chip, key, t_chip, y, bg, fg, chip_bg, chip_fg, font, font2 |
| phone-cards | the user's own clips in phone frames: `float` (3 tilted cards pop in, drift), `orbit` (circle the head), `compare` (2 cards with BEFORE/AFTER chips and badges like "2:51" or "Week 6") | layout, video1–3 (paths), start1–3, label1/2, badge1/2, y, card_w, frame, chip_bg, chip_fg |

**Text behind the speaker (and orbit behind the head):** `motion_render.py cutout <A-roll file> <out.mov> --in <src_in> --len <seconds>` makes the person alone on alpha (~40 s per second of footage on CPU, so keep the beat to 1–3 s). The editor puts the overlay on its overlay track and the cutout on a video track **above** it, at the same `at`, scale and x/y as that A-roll segment, so the words or cards pass behind the person. Place text so the head covers at most about a third of the letters.

**Section rhythm:** between list sections, use a quick whip/blur transition on the cut (CapCut "Blur" or "Swipe", 0.3 s) and change the framing (wide ↔ punch-in), so each section reads as new.

## Premium motion kit (craft rules in `motion-designer.md`, built 2026-10-19)
Effects and motion only: `font` and every colour are vars set from the client's brand and the mood; defaults are neutral greys. 9:16 at `height` 1920 (1350 for 4:5); `scale` resizes. Each change has a cause (a spoken word, a click, a beat).
| Template | Use for | Key vars |
|---|---|---|
| data-viz | data that moves: `bars` fill while numbers count, then the winner takes the accent and the rest step back; `ring` (1–3 rings close around counting %); `line` draws left to right, the number and caption read the value under the head | mode, values (a\|b), labels, title, prefix, suffix, decimals, max, winner (max/last/first/index/none), t_start, count_dur, x, y, width, bg, fg, muted, accent, font |

## Sound effects
- 19 sounds in `sfx\` (Pixabay licence: commercial use, no attribution): whoosh, whoosh-short, whoosh-cinematic, pop, click, click-soft, ping, chime, notification, sparkle, impact-bass-1/2, riser, glitch-1/2/3, typing, key-press, error.
- Each template has a tuned default cue in `sfx_defaults.json`. Overlays opt in with `"sfx": "default"`.
- Placement is automatic (`tools\plan_build.py` → `sfx_cues`): trimmed, kept under the VO, spread over 3 sound tracks so nothing overlaps, stacked whooshes merged, and every cue on its visual beat.

## Placement rules
- Keep overlays off faces and off the product's label.
- Keep the bottom ~400px free for captions (except CTA and end card), unless kinetic titles replace captions.
- Kinetic titles sit at chest height (top ≈ 1080). UI cards sit beside the hands or product.
- Text uses the script's words or brief-approved claims only, in the client's colours and fonts.

If nothing here fits, or the user brings a reference style to match, ask the **motion-designer** agent to create new templates.
