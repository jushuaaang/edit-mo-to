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
