// Every word the app adds for beginners lives here, so a second language (Task B2) can sit next to it.
//
//   t(key, vars)   the line for a dotted key ("why.timing"), with {name} filled from vars; an unknown key shows itself
//   label(id, data) a short code on screen in words: SB-5 -> "Shot 5", CHAR-1 -> the character's name or "Character 1",
//                  V02 -> "Clip 2", P3 -> "Prompt 3"; anything else as it is. Files, targets and data-* keep the codes.
//   timeTitle(text) "2:12" or "0:00–2:12" in words (seconds:frames at 30 fps), or null when it is not a time
//
// WORDS between the two marker comments is plain JSON (tests read it): double quotes, no trailing commas.
/* WORDS-START */
export const WORDS = {
  "step": {
    "brief": "Brief", "script": "Script", "storyboard": "Storyboard", "voiceover": "Voiceover",
    "timing": "Timing & cleanup", "prompts": "B-roll & prompts", "clips": "Clips", "build": "Build & QA",
    "review": "Review", "captions": "Captions", "music": "Music", "export": "Export"
  },
  "why": {
    "brief": "Claude reads the client's brief first, so every video follows their rules.",
    "script": "Claude writes the words the voice will say, following the brief.",
    "storyboard": "You see every shot as a picture before any video is made, so changes are quick and cheap.",
    "voiceover": "The recorded voice sets the timing of the whole video.",
    "timing": "Claude matches your voiceover to the script so cuts land on the words.",
    "prompts": "Claude writes a prompt for each extra shot, so you can make the clips.",
    "clips": "You make the video clips from the prompts. Claude checks each clip for problems.",
    "build": "Claude puts everything together in CapCut and checks the result.",
    "review": "You watch the video in CapCut and say what to change.",
    "captions": "Words on screen help people follow the video without sound.",
    "music": "Music sets the mood under the voice.",
    "export": "You save the finished videos from CapCut, ready to send."
  },
  "time": {
    "brief": "About 5 minutes.", "script": "About 5 minutes.",
    "storyboard": "About 20 minutes, mostly making the pictures.", "voiceover": "About 10 minutes.",
    "timing": "About 1 minute.", "prompts": "About 5 minutes.", "clips": "About 30 minutes, mostly making the clips.",
    "build": "About 10 minutes.", "review": "About 15 minutes.", "captions": "About 5 minutes.",
    "music": "About 5 minutes.", "export": "About 5 minutes."
  },
  "help": {
    "button": "What does {word} mean?",
    "row": "Words on this page:",
    "temp_en": "A temporary English track so you can follow a video in another language. Delete it before export.",
    "a_roll": "The main footage: the person talking to the camera.",
    "b_roll": "Extra shots that play over the voice, like the product or a close-up.",
    "keyframe": "A still picture of one shot. The video clip is made from it.",
    "timeline": "One version of the video in CapCut. Each hook gets its own timeline.",
    "vo": "Voiceover (VO): the recorded voice that reads the script.",
    "character_sheet": "One picture of a character from several sides, so they look the same in every shot.",
    "question": "Claude stops here and waits for your answer before it goes on.",
    "time": "Times are seconds:frames. 2:12 means 2 seconds and 12 frames (30 frames = 1 second).",
    "model": "The AI on Higgsfield that makes the clip. Each one has its own limits, like how long a clip can be.",
    "prompt": "The text you paste into the AI site to make a picture or a clip.",
    "time_value": "{s} seconds and {f} frames (30 frames = 1 second)",
    "time_long": "{m} minutes, {s} seconds and {f} frames (30 frames = 1 second)",
    "time_range": "{from} to {to}"
  },
  "word": {
    "temp_en": "TEMP_EN", "a_roll": "A-roll", "b_roll": "B-roll", "keyframe": "keyframe", "timeline": "timeline",
    "vo": "voiceover", "character_sheet": "character sheet", "question": "Claude's question", "time": "the times",
    "model": "model", "prompt": "prompt"
  },
  "label": {
    "shot": "Shot {n}", "character": "Character {n}", "clip": "Clip {n}", "prompt": "Prompt {n}",
    "ai": "AI clip {n}", "client": "Client clip {n}",
    "two": "{a} and {b}", "many": "{rest} and {last}", "more": "{n} more"
  },
  "now": {
    "you": "You", "claude": "Claude", "none": "Status",
    "capcut": "Your turn: quit CapCut completely, then press “CapCut is closed” on the {step} page.",
    "pictures": "Your turn: make the pictures for {shots}, then drop each one on its card.",
    "pictures_question": "Your turn: make the pictures for {shots} and drop each one on its card, or answer Claude's question on the {step} page.",
    "voiceover": "Your turn: drop the voiceover file on the Voiceover page.",
    "question": "Your turn: answer Claude's question on the {step} page.",
    "answered": "You answered Claude's question on the {step} page. Claude picks it up next.",
    "waiting": "Your turn: the {step} page needs you.",
    "working": "Claude is working on {step}. Nothing to do yet.",
    "error": "Something went wrong in {step}. Tell Claude in the box below.",
    "error_card": "Something went wrong in {step}. Open it and tell Claude.",
    "done": "This video is finished.",
    "next": "Next: {step}. Claude starts it when it gets there.",
    "not_listening": "Claude isn't listening right now. Your answer is saved.",
    "not_listening_ask": "Claude isn't listening right now. You can still answer: it's saved until Claude checks."
  },
  "alert": {
    "notify_title": "Claude needs you: {step}",
    "title_count": "({n}) {title}"
  },
  "settings": {
    "alerts_h": "Tell me when Claude needs me",
    "alerts_p": "When Claude asks you something new, this computer can let you know. Saved on this computer only.",
    "notify": "Pop-up when Claude needs me",
    "notify_hint": "Your browser asks once if it may show pop-ups, the first time you click after Claude asks something.",
    "notify_blocked": "Your browser blocks pop-ups for this page. Allow them in the browser's site settings to get them.",
    "sound": "Sound",
    "sound_hint": "A short, soft sound.",
    "loading": "Loading…",
    "saved": "Saved.",
    "not_saved": "Not saved: {why}"
  },
  "practice": {
    "title": "New here? Try a practice video first.",
    "what": "A 10-second practice video made from a clip of you talking. Same 12 steps as a real job, about 15 to 25 minutes, and no client sees it.",
    "type": "In Claude, type:",
    "copy": "Copy"
  },
  "page": {
    "why_label": "Why this step"
  },
  "storyboard": {
    "open_close": "Open {name} close up",
    "picture_of": "Picture of {name}",
    "drop": "Drop the picture for {name}",
    "comment_on": "Comment on {name}",
    "comment_what": "What should change in {name}?",
    "comment_dialog": "A comment on {name}…",
    "missing": "{n} shots have no keyframe yet ({names}). Approve anyway?",
    "missing_one": "1 shot has no keyframe yet ({names}). Approve anyway?",
    "char_title": "{name} · Character sheet",
    "save_as": "saved as storyboard/{id}.png, or choose a file",
    "prev": "← {name}",
    "next": "{name} →",
    "prev_plain": "← Previous",
    "next_plain": "Next →",
    "acted": "{word} {name}. {after}"
  },
  "prompts": {
    "unknown_model": "We don't know this model's limits yet, so Claude uses safe settings: clips {min} to {max} seconds, up to {attach} pictures.",
    "unknown_model_plain": "We don't know this model's limits yet, so Claude uses safe settings.",
    "unverified": "Nobody has checked the limits of {model} yet. Claude checks the prompts and tells you if something may not fit.",
    "no_table": "The list of video sites couldn't be loaded. Ask Claude which site to use.",
    "regen": "{name}, to make it again in your video site"
  }
};
/* WORDS-END */

const at = (key) => key.split(".").reduce((o, k) => (o && typeof o === "object" ? o[k] : undefined), WORDS);

/** The line for `key` with {name} filled from vars. A missing key shows the key, so a gap is visible, never blank. */
export function t(key, vars = {}) {
  const s = at(key);
  if (typeof s !== "string") return key;
  return s.replace(/\{(\w+)\}/g, (m, k) => (vars[k] === undefined || vars[k] === null ? m : String(vars[k])));
}

const LIST_MAX = 4;  // longer lists end "… and 3 more"

/** "Shot 5", "Shot 5 and Shot 6", "Shot 5, Shot 6 and Shot 8", "Shot 1, Shot 2, Shot 3 and 9 more". */
export function listText(names) {
  if (names.length > LIST_MAX) {
    const shown = names.slice(0, LIST_MAX - 1);
    return t("label.many", { rest: shown.join(", "), last: t("label.more", { n: names.length - shown.length }) });
  }
  if (names.length <= 1) return names[0] || "";
  if (names.length === 2) return t("label.two", { a: names[0], b: names[1] });
  return t("label.many", { rest: names.slice(0, -1).join(", "), last: names[names.length - 1] });
}

const CODES = [
  [/^SB-(\d+)$/i, "label.shot"], [/^CHAR-(\d+)$/i, "label.character"], [/^V0*(\d+)$/i, "label.clip"],
  [/^P0*(\d+)$/i, "label.prompt"], [/^AI-0*(\d+)$/i, "label.ai"], [/^C-0*(\d+)$/i, "label.client"],
];

/** A code in words. CHAR-n uses the character's name from storyboard.json when known (the part before a comma). */
export function label(id, data) {
  const s = String(id ?? "").trim();
  if (/^CHAR-\d+$/i.test(s)) {
    const c = (Array.isArray(data?.storyboard?.characters) ? data.storyboard.characters : []).find((x) => x?.id === s);
    const name = typeof c?.name === "string" ? c.name.split(",")[0].trim() : "";
    if (name) return name;
  }
  for (const [re, key] of CODES) {
    const m = re.exec(s);
    if (m) return t(key, { n: Number(m[1]) });
  }
  return s;
}

const ONE = /^(\d+):(\d{2})(?::(\d{2}))?$/;

function oneTime(s) {
  const m = ONE.exec(s.trim());
  if (!m) return null;
  return m[3] === undefined ? t("help.time_value", { s: Number(m[1]), f: Number(m[2]) })
    : t("help.time_long", { m: Number(m[1]), s: Number(m[2]), f: Number(m[3]) });
}

/** "2 seconds and 12 frames (30 frames = 1 second)" for "2:12"; a range "0:00–2:12" reads "… to …". Else null. */
export function timeTitle(text) {
  const parts = String(text ?? "").split(/\s*[–-]\s*/);
  if (parts.length === 1) return oneTime(parts[0]);
  if (parts.length !== 2) return null;
  const [a, b] = parts.map((p) => oneTime(p));
  if (!a || !b) return null;
  const strip = (x) => x.replace(/ \(30 frames = 1 second\)$/, "");
  return `${t("help.time_range", { from: strip(a), to: strip(b) })} (30 frames = 1 second)`;
}
