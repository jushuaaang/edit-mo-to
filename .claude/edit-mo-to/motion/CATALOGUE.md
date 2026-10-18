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
