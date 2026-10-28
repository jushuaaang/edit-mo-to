// "What to do now" and "Tell me when Claude needs me" (spec "Beginner friendly").
//
//   nextStep(data, where) -> {who: "you"|"claude"|"none", key, text}   from the /api/job reply only: the open
//                            question, step states, the keyframes on disk, the editor's uploads and `listening`.
//                            where: "page" (a step page) or "card" (a dashboard card).
//   nowStrip(data, where)    the line as an element; every look also has a word (a chip), never colour alone.
//   watchQuestion(folder, data)  call after each poll of the open video: when the open question's id changes to a new
//                            one (not on the first reply for a folder) a pop-up and a soft sound, if switched on; the tab
//                            title carries "(1)" while a question is open and unanswered.
//   loadPrefs(api) / savePrefs(api, patch) / getPrefs()   this computer's switches (GET/POST /api/prefs)
import { h, chip, STEPS, stepTitle } from "./ui.js";
import { t, label, listText } from "./words.js";
import { picturesToMake } from "./board.js";

// ---------- the rule table: the first rule whose test is true wins (keys are WORDS.now.*) ----------

const answerOf = (data, gate, q) => (data?.events || []).some((e) => e.type === "answer" && e.gate === gate.id
  && e.target === q.id && !e.stale);
export const unanswered = (data, gate) => (gate?.questions || []).filter((q) => !answerOf(data, gate, q));
const stateOf = (data, s) => data?.job?.steps?.[s]?.state || "pending";
const firstIn = (data, state) => STEPS.find((s) => stateOf(data, s) === state) || null;

/** The pictures that can be made now (board.js picturesToMake: a prompt is written; character sheets first), in words. */
export const missingPictures = (data) => picturesToMake(data).map((it) => label(it.id, data));

/** A voice file is in vo/ (the server lists it, whether it came through the app or was copied in from Finder). */
const hasVoiceFile = (data) => Array.isArray(data?.vo) && data.vo.length > 0;

export const RULES = [
  { key: "now.answered", who: "claude", when: (d, g) => g && !unanswered(d, g).length },
  { key: "now.capcut", who: "you", when: (d, g) => g && unanswered(d, g).some((q) => q.id === "capcut_closed") },
  { key: "now.pictures_question", who: "you", when: (d, g) => g?.step === "storyboard" && missingPictures(d).length },
  { key: "now.question", who: "you", when: (d, g) => Boolean(g) },
  { key: "now.pictures", who: "you", when: (d) => stateOf(d, "storyboard") === "waiting" && missingPictures(d).length },
  { key: "now.voiceover", who: "you", when: (d) => stateOf(d, "voiceover") === "waiting" && !hasVoiceFile(d) },
  { key: "now.waiting", who: "you", when: (d) => firstIn(d, "waiting") },
  { key: "now.working", who: "claude", when: (d) => firstIn(d, "working") },
  { key: "now.error", who: "you", when: (d) => firstIn(d, "error") },
  { key: "now.done", who: "none", when: (d) => STEPS.every((s) => ["done", "skipped"].includes(stateOf(d, s))) },
  { key: "now.next", who: "none", when: () => true },
];

/** Which step the line is about: the question's, else the first waiting / working / error / not-started step. */
function stepFor(data, gate, key) {
  if (gate) return gate.step;
  const by = { "now.pictures": "storyboard", "now.voiceover": "voiceover", "now.waiting": firstIn(data, "waiting"),
    "now.working": firstIn(data, "working"), "now.error": firstIn(data, "error") };
  return by[key] || firstIn(data, "pending");
}

export function nextStep(data, where = "page") {
  if (!data?.job) return { who: "none", key: "", text: "" };
  const gate = data.job.gate || null;
  const rule = RULES.find((r) => r.when(data, gate));
  const step = stepFor(data, gate, rule.key);
  const key = rule.key === "now.error" && where === "card" ? "now.error_card" : rule.key;
  let text = t(key, { step: stepTitle(step), shots: listText(missingPictures(data)) });
  if (gate && !data.listening) {  // "saved" only once an answer is really in the inbox
    const some = (gate.questions || []).length > unanswered(data, gate).length;
    text += ` ${t(some ? "now.not_listening" : "now.not_listening_ask")}`;
  }
  return { who: rule.who, key, text };
}

const LOOK = { you: ["you", "now.you"], claude: ["wait", "now.claude"], none: ["mute", "now.none"] };

export function nowStrip(data, where = "page") {
  const n = nextStep(data, where);
  if (!n.text) return null;
  const [status, word] = LOOK[n.who];
  return h("div", { class: `nowline ${n.who}`, role: "status", "data-now": n.key }, chip(t(word), status), h("span", {}, n.text));
}

// ---------- this computer's switches ----------

let prefs = { notify: true, sound: true };

export const getPrefs = () => ({ ...prefs });

export async function loadPrefs(api) {
  try { prefs = { ...prefs, ...(await api("/api/prefs")) }; } catch { /* defaults; Settings shows the error */ }
  return getPrefs();
}

/** Saves on the server; resolves to what the server now holds (the switches show only that). */
export async function savePrefs(api, patch) {
  prefs = { ...prefs, ...(await api("/api/prefs", { body: patch })) };
  return getPrefs();
}

// ---------- alerts ----------

const seen = new Map();  // folder -> the open question's id the last poll saw (null = none)
let count = 0, armed = false, audio = null;

const ASKED = "emt-notify-asked";
const asked = () => { try { return localStorage.getItem(ASKED) === "1"; } catch { return false; } };

/** The tab title with "(1) " while a question is open and unanswered. */
export function titled(base) {
  const plain = String(base).replace(/^\(\d+\)\s*/, "");
  return count ? t("alert.title_count", { n: count, title: plain }) : plain;
}

/** After a question opens, the editor's first click asks (once) whether pop-ups may show, and unlocks the sound. */
function arm() {
  if (armed) return;
  armed = true;
  document.addEventListener("click", () => {
    armed = false;
    try { audio = audio || new (window.AudioContext || window.webkitAudioContext)(); audio.resume?.(); } catch { audio = null; }
    if (!prefs.notify || asked() || !("Notification" in window) || Notification.permission !== "default") return;
    try { localStorage.setItem(ASKED, "1"); } catch { /* asked for this page load only */ }
    try { Notification.requestPermission(); } catch { /* old browsers: nothing */ }
  }, { once: true, capture: true });
}

function softSound() {
  try {
    audio = audio || new (window.AudioContext || window.webkitAudioContext)();
    const now = audio.currentTime, osc = audio.createOscillator(), gain = audio.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(660, now);
    osc.frequency.linearRampToValueAtTime(880, now + 0.18);
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(0.08, now + 0.03);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.45);
    osc.connect(gain).connect(audio.destination);
    osc.start(now);
    osc.stop(now + 0.5);
  } catch { /* no sound on this browser */ }
}

function popUp(gate) {
  if (!prefs.notify || !("Notification" in window) || Notification.permission !== "granted") return;
  try {
    const n = new Notification(t("alert.notify_title", { step: stepTitle(gate.step) }),
      { body: typeof gate.title === "string" ? gate.title : "", tag: `emt-${gate.id}` });
    n.onclick = () => { window.focus(); n.close(); };
  } catch { /* the page keeps the title count */ }
}

export function watchQuestion(folder, data) {
  if (!folder || !data?.job) return;
  const gate = data.job.gate || null;
  const id = gate?.id || null;
  const first = !seen.has(folder);
  const before = seen.get(folder);
  seen.set(folder, id);
  count = gate && unanswered(data, gate).length ? 1 : 0;
  document.title = titled(document.title);
  if (count) arm();
  if (!first && id && id !== before) {
    popUp(gate);
    if (prefs.sound) softSound();
  }
}
