// Storyboard (step 3, optional; spec "Storyboard"): the board comes first and the images fill in. Character sheet
// cards on top, then a card per shot with its status, line, time, shot type and keyframe prompt (Copy prompt).
// Images are dropped on a card (saved as storyboard/SB-n.png or CHAR-n.png; a file saved there from outside shows on
// the next poll). Clicking an image opens the `shot` dialog (dialogs.js). Gates: character sheet saved (`character_sheet`,
// a confirm the gate bar shows as "It's saved"); approve the direction (`approve`). Approve all answers `approve` when
// the open gate asks it; otherwise it sends an `approve` event that Claude confirms at the approval gate.
//
// Events: edits `edit` "storyboard:<id>:prompt|visual"; comments `comment` "storyboard:<id>" (or "storyboard" for the
// whole board); `approve` "storyboard:<id>" / "storyboard"; Request change `action` "storyboard:<id>"; Got flagged
// `action` "storyboard:<id>:flagged" (steppage.flaggedBox, on a card with a prompt).
// Every string from storyboard.json, events and paths reaches the DOM as text through h(). On screen a card is "Shot 5"
// or the character's name (words.js label), never its code; files and event targets keep SB-n / CHAR-n.
import { h, chip, pendingChip, toast, dropZone, helpTip, timeText, staleText } from "../ui.js";
import { t, label } from "../words.js";
import { boardItems, isClient, promptOf, needsImage } from "../board.js";
import { stepPage, stateOf, openGate, gateAnswer, answerGate, pendingFor, copyButton, waitingText, flaggedBox } from "../steppage.js";

const STEP = "storyboard";
const FILTERS = ["all", "need", "changed", "comments"];  // words: WORDS.storyboard.f_<filter>

// GUI-only view state, kept across re-renders after a poll: {filter, selected, confirm, open: Set of comment boxes}.
const views = new Map();
const viewOf = (folder) => {
  if (!views.has(folder)) views.set(folder, { filter: "all", selected: null, confirm: false, open: new Set() });
  return views.get(folder);
};

// ---------- reading the board (shared with the shot dialog) ----------

const str = (v) => (typeof v === "string" ? v : v === null || v === undefined ? "" : String(v));
const handledSet = (data) => new Set(data?.job?.handled || []);

// boardItems, isClient, promptOf and needsImage live in board.js (the "what to do now" strip uses the same rule).
export { boardItems, isClient, promptOf };

/** /api/file URL of the keyframe, or null. `v` is the file's mtime, so a keyframe replaced under the same name (in the
 *  GUI or from outside it) gets a new URL and the new picture shows. */
export function keyframeUrl(data, id) {
  const path = data?.keyframes?.[id];
  if (typeof path !== "string" || !path) return null;
  const v = data?.keyframe_mtimes?.[id];
  return `/api/file?path=${encodeURIComponent(path)}&v=${encodeURIComponent(str(v ?? 0))}`;
}

/** This item's comment events (newest last); `open` = not handled by Claude yet. */
export function commentsFor(data, id) {
  const done = handledSet(data);
  return (data?.events || []).filter((e) => e.type === "comment" && e.target === `${STEP}:${id}`)
    .map((e) => ({ ...e, open: !done.has(e.seq) }));
}

/** [word, chip status] for a card (every chip has a word). "approved" only from the board itself (Claude applied it);
 *  an approve the editor sent that Claude hasn't handled yet is "approval sent" (a handled one, or one from an earlier
 *  round, never outranks "changed" or "comment open"). */
export function statusOf(data, it) {
  if (it.item?.status === "approved") return [t("storyboard.st_approved"), "ok"];
  const done = handledSet(data);
  const approveSent = (data?.events || []).some((e) => e.type === "approve" && !e.stale && !done.has(e.seq)
    && (e.target === `${STEP}:${it.id}` || e.target === STEP));
  if (approveSent) return [t("storyboard.st_sent"), "wait"];
  if (it.item?.status === "changed") return [t("storyboard.st_changed"), "opt"];
  if (commentsFor(data, it.id).some((c) => c.open)) return [t("storyboard.st_comment"), "you"];
  if (data?.keyframes?.[it.id]) return [t("storyboard.st_image"), "wait"];
  if (isClient(it)) return [t("storyboard.st_client"), "mute"];
  return promptOf(it) ? [t("storyboard.st_ready"), "mute"] : [t("storyboard.st_char"), "mute"];
}

/** The shot's type in words: "AI · Close-up · push-in", "Client clip · take.mp4 @ 12.4 s", "Graphic · cta-pill". */
export function shotText(it) {
  if (it.kind === "char") return t("storyboard.char_sheet");
  const s = it.item?.shot || {};
  if (s.type === "client") {
    const file = str(s.file).split(/[\\/]/).pop();
    return [t("storyboard.client_clip"), file ? `${file}${s.t !== undefined && s.t !== null ? ` @ ${str(s.t)} s` : ""}` : null].filter(Boolean).join(" · ");
  }
  if (s.type === "graphic") return [t("storyboard.graphic"), str(s.template)].filter(Boolean).join(" · ");
  return [t("storyboard.ai"), ...["framing", "subject", "action", "camera"].map((k) => str(s[k])).filter(Boolean)].join(" · ");
}

/** The open storyboard gate's approval question: the question with id "approve" (never matched by its wording). */
export function approvalQuestion(gate) {
  const qs = gate?.questions || [];
  return qs.find((q) => q.id === "approve") || null;
}

/** The character-sheet gate question (a confirm; the gate bar offers "It's saved"). */
export const CHAR_Q = "character_sheet";

/** Send one event; resolve true when stored. */
export async function sendEvent(ctx, event, okText) {
  try {
    const ev = await ctx.send({ step: STEP, ...event });
    toast(okText || waitingText(ctx.data));
    return ev || true;
  } catch (e) {
    toast(e.message || t("common.not_sent"));
    return null;
  }
}

// ---------- cards ----------

function imageSlot(ctx, data, it, zone) {
  const url = keyframeUrl(data, it.id);
  if (url) {
    return h("button", { class: "sbimg", type: "button", "aria-label": t("storyboard.open_close", { name: label(it.id, data) }),
      onclick: () => ctx.openDialog("shot", { id: it.id }) },
    h("img", { src: url, alt: t("storyboard.picture_of", { name: label(it.id, data) }), loading: "lazy" }));
  }
  if (isClient(it)) {
    return h("button", { class: "sbimg empty", type: "button", "aria-label": t("storyboard.open_close", { name: label(it.id, data) }),
      onclick: () => ctx.openDialog("shot", { id: it.id }) }, h("span", {}, t("storyboard.client_footage")), h("small", {}, t("storyboard.no_keyframe_needed")));
  }
  return h("div", { class: "sbimg empty drop-slot" }, zone);
}

function commentBox(ctx, data, it, view) {
  const id = it.id;
  const open = view.open.has(id);
  const name = label(id, data);
  const ta = h("textarea", { class: "f", rows: 2, "data-key": `sb:comment:${id}`, "aria-label": t("storyboard.comment_on", { name }),
    placeholder: t("storyboard.comment_what", { name }) });
  const btn = h("button", { class: "btn sm pri", type: "button" }, t("common.send"));
  btn.addEventListener("click", async () => {
    const text = ta.value.trim();
    if (!text) { ta.focus(); return; }
    btn.disabled = true;
    if (await sendEvent(ctx, { type: "comment", target: `${STEP}:${id}`, text })) { ta.value = ""; view.open.delete(id); }
    btn.disabled = false;
  });
  const det = h("details", { class: "sbcomment", open }, h("summary", { class: "btn sm" }, t("storyboard.comment")),
    h("div", { class: "stack" }, ta, h("div", { class: "row" }, btn)));
  det.addEventListener("toggle", () => { if (det.open) view.open.add(id); else view.open.delete(id); });
  return det;
}

function promptBlock(ctx, data, it) {
  const text = promptOf(it);
  const pend = pendingFor(data, `${STEP}:${it.id}:prompt`).length ? pendingChip() : null;
  if (text) {
    return h("div", { class: "sbprompt" }, h("pre", { class: "prompt" }, text),
      h("div", { class: "row" }, copyButton(text, t("storyboard.copy_prompt")), pend), flaggedBox(ctx, data, STEP, it.id, "card"));
  }
  if (isClient(it)) return h("p", { class: "hint" }, t("storyboard.client_no_prompt"));
  return h("p", { class: "hint" }, t(it.kind === "char" ? "storyboard.no_prompt_char" : "storyboard.no_prompt_yet"), pend);
}

function card(ctx, data, it, view) {
  const [word, status] = statusOf(data, it);
  const b = it.item;
  const name = label(it.id, data);
  const zone = isClient(it) ? null : dropZone("keyframe", ctx, { id: it.id, label: data?.keyframes?.[it.id] ? t("storyboard.replace") : t("storyboard.drop", { name }) });
  const open = commentsFor(data, it.id).filter((c) => c.open).length;
  const el = h("article", { class: `sbcard${it.kind === "char" ? " char" : ""}${view.selected === it.id ? " sel" : ""}`,
    "data-id": it.id, "aria-label": `${name}, ${word}` },
  imageSlot(ctx, data, it, zone),
  h("div", { class: "sbbody" },
    h("div", { class: "row spread" }, h("span", { class: "row" }, h("b", {}, name), chip(word, status)),
      b.est ? timeText(str(b.est), { class: "mono hint" }) : null),
    it.kind === "char" ? h("div", { class: "sbline" }, str(b.name) || t("storyboard.character")) : null,
    it.kind === "shot" && b.line ? h("q", { class: "sbline" }, str(b.line)) : null,
    it.kind === "shot" && b.en ? h("div", { class: "hint" }, t("storyboard.english_temp", { text: str(b.en) })) : null,
    h("div", { class: "hint" }, shotText(it)),
    promptBlock(ctx, data, it),
    h("div", { class: "row sbfoot" }, commentBox(ctx, data, it, view),
      h("button", { class: "btn sm", type: "button", onclick: () => { view.selected = it.id; ctx.openDialog("shot", { id: it.id }); } }, t("storyboard.details")),
      open ? h("span", { class: "hint" }, t(open > 1 ? "storyboard.comments_open" : "storyboard.comments_open_one", { n: open })) : null,
      pendingFor(data, `${STEP}:${it.id}`).length ? pendingChip() : null),
    zone && data?.keyframes?.[it.id] ? h("div", { class: "sbreplace" }, zone) : null));
  if (zone) {  // a file dropped anywhere on the card goes to the card's drop zone
    el.addEventListener("dragover", (e) => { e.preventDefault(); el.classList.add("over"); });
    el.addEventListener("dragleave", (e) => { if (!el.contains(e.relatedTarget)) el.classList.remove("over"); });
    el.addEventListener("drop", (e) => {
      el.classList.remove("over");
      if (zone.contains(e.target)) return;
      e.preventDefault();
      zone.dispatchEvent(new DragEvent("drop", { dataTransfer: e.dataTransfer, cancelable: true }));
    });
  }
  return el;
}

// ---------- toolbar and approval ----------

const FILTER_FN = {
  all: () => true,
  need: (data, it) => needsImage(data, it),
  changed: (data, it) => it.item?.status === "changed",
  comments: (data, it) => commentsFor(data, it.id).some((c) => c.open),
};

function approveAll(ctx, data, items, view, rerender) {
  const gate = openGate(data, STEP);
  const q = approvalQuestion(gate);
  const sent = q ? gateAnswer(data, gate, q.id) : null;
  // no approval question open (no gate, or the character-sheet / keyframes gate): an `approve` event, which Claude
  // takes as the default and confirms at the approval gate; it never replaces that gate
  const pend = !q && pendingFor(data, STEP).some((e) => e.type === "approve");
  if (sent) {
    return h("span", { class: "row" }, chip(t(sent.value === false ? "storyboard.not_approved_sent" : "storyboard.approved_waiting"), "wait"));
  }
  if (pend) return h("span", { class: "row" }, chip(t("storyboard.approve_all_sent"), "wait"), pendingChip());
  const missing = items.filter((it) => it.kind === "shot" && needsImage(data, it)).map((it) => label(it.id, data));
  const status = h("span", { class: "hint", role: "status" });
  const send = async (btns) => {
    btns.forEach((b) => { b.disabled = true; });
    try {
      const ev = q ? await answerGate(ctx, gate, q.id, true) : await ctx.send({ type: "approve", step: STEP, target: STEP });
      view.confirm = false;
      if (ev?.stale) { status.textContent = staleText(); return; }
      toast(waitingText(ctx.data));
    } catch (e) {
      status.textContent = e.message || t("common.not_sent");
      btns.forEach((b) => { b.disabled = false; });
    }
  };
  const btn = h("button", { class: "btn pri", type: "button" }, t("storyboard.approve_all"));
  btn.addEventListener("click", () => {
    if (missing.length) { view.confirm = true; rerender(); } else send([btn]);
  });
  if (!view.confirm || !missing.length) return h("span", { class: "row" }, btn, status);
  const n = missing.length;
  const anyway = h("button", { class: "btn pri sm", type: "button" }, t("storyboard.approve_anyway"));
  const wait = h("button", { class: "btn sm", type: "button",
    onclick: () => { view.confirm = false; view.filter = "need"; rerender(); } }, t("storyboard.wait_images"));
  anyway.addEventListener("click", () => send([anyway, wait]));
  return h("div", { class: "sbconfirm", role: "alert" },
    h("span", {}, t(n > 1 ? "storyboard.missing" : "storyboard.missing_one", { n, names: missing.join(", ") }), helpTip("keyframe")),
    h("span", { class: "row" }, anyway, wait, status));
}

function toolbar(ctx, data, items, view, rerender) {
  const seg = (label, opts) => h("div", { class: "seg", role: "group", "aria-label": label }, opts);
  const views2 = seg(t("storyboard.view"), [
    h("button", { type: "button", class: "on", "aria-pressed": "true" }, t("storyboard.grid")),
    h("button", { type: "button", "aria-pressed": "false", onclick: () => {
      const id = view.selected && items.some((it) => it.id === view.selected) ? view.selected
        : (items.find((it) => it.kind === "shot") || items[0])?.id;
      if (id) ctx.openDialog("shot", { id });
    } }, t("storyboard.detail"))]);
  const filters = seg(t("storyboard.show"), FILTERS.map((key) => {
    const n = items.filter((it) => FILTER_FN[key](data, it)).length;
    return h("button", { type: "button", class: view.filter === key ? "on" : null, "aria-pressed": String(view.filter === key),
      onclick: () => { view.filter = key; rerender(); } }, `${t(`storyboard.f_${key}`)} ${n}`);
  }));
  const share = h("a", { class: "btn", href: `/api/file?path=${encodeURIComponent(`${ctx.folder}/storyboard/storyboard.html`)}`,
    target: "_blank", rel: "noopener" }, t("storyboard.share"));
  return h("div", { class: "sbbar" }, h("div", { class: "row" }, views2, filters),
    h("div", { class: "row" }, share, approveAll(ctx, data, items, view, rerender)));
}

// ---------- whole-board notes ----------

function notesBox(ctx, data) {
  const done = handledSet(data);
  const notes = (data?.events || []).filter((e) => e.type === "comment" && e.target === STEP);
  const ta = h("textarea", { class: "f", id: "sb-notes", rows: 3, "data-key": "sb:notes",
    placeholder: t("storyboard.notes_ph") });
  const btn = h("button", { class: "btn sm pri", type: "button" }, t("storyboard.send_notes"));
  btn.addEventListener("click", async () => {
    const text = ta.value.trim();
    if (!text) { ta.focus(); return; }
    btn.disabled = true;
    if (await sendEvent(ctx, { type: "comment", target: STEP, text })) ta.value = "";
    btn.disabled = false;
  });
  return h("section", { class: "card" }, h("h3", {}, h("label", { for: "sb-notes" }, t("storyboard.notes_h"))),
    notes.length ? h("ul", { class: "files" }, notes.slice(-6).map((e) => h("li", {}, h("span", {}, str(e.text)),
      chip(t(done.has(e.seq) ? "common.claude_has_it" : "common.sent_waiting"), done.has(e.seq) ? "ok" : "wait")))) : null,
    ta, h("div", { class: "row", style: "margin-top:8px" }, btn));
}

// ---------- page ----------

/** Approve all is drawn when the step's body shows (not "pending") and storyboard.json was read. */
export const approveAllDrawn = (data) => Boolean(data?.storyboard) && stateOf(data, STEP) !== "pending";

export function render(root, data, ctx) {
  const view = viewOf(ctx.folder);
  const items = boardItems(data);
  const gate = openGate(data, STEP);
  const q = approvalQuestion(gate);
  const rerender = () => {  // a filter or the Approve-all line changed: draw again, keeping what was typed
    const typed = [...root.querySelectorAll("[data-key]")].map((el) => [el.dataset.key, el.value]);
    root.replaceChildren();
    render(root, ctx.data || data, ctx);
    for (const [key, value] of typed) {
      const el = [...root.querySelectorAll("[data-key]")].find((x) => x.dataset.key === key);
      if (el && value) el.value = value;
    }
  };
  stepPage(root, STEP, data, ctx, {
    // Approve all answers the approval question (with the missing-keyframe check), so the gate bar hides it only
    // when Approve all is drawn on this render: the board exists and the step's body shows. Otherwise the gate bar asks it.
    hide: q && approveAllDrawn(data) ? [q.id] : [],
    labels: { [CHAR_Q]: { yes: t("storyboard.its_saved"), no: null } },
    body: () => {
      if (!data?.storyboard) {
        return [h("section", { class: "card" }, h("h3", {}, t("step.storyboard")), h("p", { class: "hint" }, t("storyboard.empty_p")))];
      }
      const shown = items.filter((it) => FILTER_FN[view.filter](data, it));
      return [
        toolbar(ctx, data, items, view, rerender),
        h("p", { class: "hint words" }, t("help.row"), ...["keyframe", "prompt", "character_sheet", "time"].map((k) =>
          h("span", { class: "word" }, t(`word.${k}`), helpTip(k)))),
        data.storyboard.direction ? h("p", { class: "hint" }, str(data.storyboard.direction)) : null,
        shown.length ? h("div", { class: "sbgrid" }, shown.map((it) => card(ctx, data, it, view)))
          : h("section", { class: "card" }, h("p", { class: "hint" }, t("storyboard.no_match"))),
        notesBox(ctx, data),
      ].filter(Boolean);
    },
  });
}
