// Reading the storyboard (storyboard/storyboard.json and the keyframes on disk), shared by the storyboard page, the
// shot dialog and the "what to do now" strip, so they all follow one rule. No DOM here.

const str = (v) => (typeof v === "string" ? v : v === null || v === undefined ? "" : String(v));

/** Character sheets then shots: [{id, kind: "char"|"shot", item}] in board order. */
export function boardItems(data) {
  const sb = data?.storyboard;
  const chars = Array.isArray(sb?.characters) ? sb.characters : [];
  const beats = Array.isArray(sb?.beats) ? sb.beats : [];
  return [...chars.map((c) => ({ id: str(c?.id), kind: "char", item: c || {} })).filter((x) => x.id),
    // a beat that lost its id in a refine keeps its card: SB-<n> by its place on the board (1-based)
    ...beats.map((b, i) => ({ id: str(b?.id) || `SB-${i + 1}`, kind: "shot", item: b || {} }))];
}

/** A client-clip beat is the client's own footage: it needs no keyframe and no prompt. */
export const isClient = (it) => it.kind === "shot" && it.item?.shot?.type === "client";

/** The real prompt, or null (null on a shot = written after the character sheets are saved). */
export const promptOf = (it) => (typeof it.item?.prompt === "string" && it.item.prompt.trim() ? it.item.prompt : null);

/** No picture on disk yet (client footage never needs one). */
export const needsImage = (data, it) => !isClient(it) && !data?.keyframes?.[it.id];

/** Is a character sheet still missing on disk? Only then does a shot's null prompt mean "waits for the character
 *  sheet"; once every sheet is saved (or there is none), a null prompt is one Claude hasn't written yet. */
export const sheetsMissing = (data) => boardItems(data).some((it) => it.kind === "char" && needsImage(data, it));

/** The pictures the editor can make now: those still missing that have a prompt. While a character sheet is missing,
 *  only the character sheets (the shots' prompts are written after them). */
export function picturesToMake(data) {
  const missing = boardItems(data).filter((it) => needsImage(data, it));
  const chars = missing.filter((it) => it.kind === "char");
  return (chars.length ? chars : missing).filter((it) => promptOf(it));
}
