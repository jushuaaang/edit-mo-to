// Reusable components for the Edit Mo To pages. No framework: each function returns a DOM element.
//
// Page modules (pages/<step>.js) get `ctx` from app.js:
//   ctx.folder                  the video folder (absolute, forward slashes)
//   ctx.send(event)             POST /api/inbox; resolves to the stored event (with seq)
//   ctx.saveGui(patch)          POST /api/gui (GUI-only state: drafts, view choices)
//   ctx.openDialog(name, args)  a dialog from dialogs.js (later build), or a plain "coming" dialog
//   extras: ctx.api(path, opts), ctx.upload(query, file, onProgress), ctx.data (latest /api/job reply),
//           ctx.go(hash)
// Inputs that carry a `data-key` keep what the editor typed when the page re-renders after a poll.
// Every word the editor reads comes from words.js (t), looked up when the element is built, so a language change
// shows on the next render.

import { t, timeTitle, label, wordsIn } from "./words.js";

export const STEPS = ["brief", "script", "storyboard", "voiceover", "timing", "prompts", "clips",
  "build", "review", "captions", "music", "export"];
export const stepTitle = (step) => (STEPS.includes(step) ? t(`step.${step}`) : step || "");  // titles: words.js

/** The step a not-started step waits for: the one before it (an optional storyboard that never ran is passed over). */
export function previousStep(step, job) {
  let i = STEPS.indexOf(step) - 1;
  if (STEPS[i] === "storyboard" && ["pending", "skipped"].includes(job?.steps?.storyboard?.state || "pending")) i -= 1;
  return i >= 0 ? STEPS[i] : null;
}

const GIB = 1024 ** 3, MIB = 1024 ** 2;
const MEDIA = ["mp3", "wav", "m4a", "aac"];
export const UPLOAD_RULES = {
  refs: { exts: ["pdf", "docx", "doc", "txt", "md", "png", "jpg", "jpeg", "webp", "gif", "mp4", "mov", "m4v", "mp3", "wav", "m4a"],
    limit: 4 * GIB, limitText: "4 GiB", where: "refs/" },
  keyframe: { exts: ["png", "jpg", "jpeg", "webp"], limit: 50 * MIB, limitText: "50 MiB", where: "storyboard/" },
  vo: { exts: MEDIA, limit: 4 * GIB, limitText: "4 GiB", where: "vo/" },
  music: { exts: MEDIA, limit: 4 * GIB, limitText: "4 GiB", where: "music/" },
};
const STEP_UPLOAD = { voiceover: "vo", music: "music" };
const KEYFRAME_ID = /^(SB|CHAR)-\d+$/;

/** [upload kind, keyframe id] for a `file` question: storyboard SB-n / CHAR-n -> keyframe, VO, music, else refs. */
export function fileTarget(step, q) {
  if (step === "storyboard" && KEYFRAME_ID.test(q.id || "")) return ["keyframe", q.id];
  return [STEP_UPLOAD[step] || "refs", undefined];
}
/** "That question closed; Claude asked something new" in the current language. */
export const staleText = () => t("gate.stale");

// ---------- tiny DOM helpers ----------

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/** h("button", {class: "btn", onclick: fn}, "Text", childNode) */
export function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else if (k === "html") el.innerHTML = v;
    else if (k in el && typeof v !== "string") el[k] = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

const ICONS = {
  home: '<path d="M3 11l9-7 9 7"/><path d="M5 10v10h14V10"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  check: '<path d="M5 12l5 5L20 7"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  alert: '<path d="M12 8v5"/><path d="M12 16.5v.5"/><circle cx="12" cy="12" r="9"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h8"/>',
  upload: '<path d="M12 16V4"/><path d="M7 9l5-5 5 5"/><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
  send: '<path d="M4 12l16-8-6 16-2-7-8-1z"/>',
  panel: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M15 4v16"/>',
  external: '<path d="M14 4h6v6"/><path d="M20 4l-9 9"/><path d="M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"/>',
  dash: '<path d="M6 12h12"/>',
};

export function icon(name) {
  const span = document.createElement("span");
  span.innerHTML = `<svg class="i" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${ICONS[name] || ""}</svg>`;
  return span.firstChild;
}

export function relTime(iso) {
  const ms = Date.parse(iso || "");
  if (Number.isNaN(ms)) return "";
  const s = Math.max(0, (Date.now() - ms) / 1000);
  if (s < 60) return t("common.now");
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

export function toast(text, ms = 2400) {
  const el = h("div", { class: "toast", role: "status" }, text);
  document.body.append(el);
  setTimeout(() => el.remove(), ms);
}

// ---------- chips ----------

/** A status chip; status is ok | wait | you | err | opt | mute. Always carries a word. */
export function chip(text, status = "mute") {
  return h("span", { class: `chip ${status || "mute"}` }, text);
}

export const STATE_CHIP = {  // state -> chip look; the word is WORDS.state.<state>
  pending: "mute", working: "wait", waiting: "you", done: "ok", skipped: "mute", error: "err",
};

/** The chip for a step state (pending | working | waiting | done | skipped | error). */
export function stepChip(state) {
  const st = STATE_CHIP[state] ? state : "pending";
  return chip(t(`state.${st}`), STATE_CHIP[st]);
}

export function pendingChip() {
  return h("span", { class: "chip wait", title: t("ui.pending_title") }, t("ui.pending"));
}

// ---------- word help (ⓘ) ----------

let tipSeq = 0;
const openTips = new Set();
const closeTips = (except) => openTips.forEach((close) => { if (close !== except) close(); });
document.addEventListener("click", (e) => { if (!e.target.closest?.(".info")) closeTips(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && openTips.size) closeTips(); });

/** A small ⓘ after a word: one plain line from WORDS.help.<key> on hover, focus or tap; Escape or a tap outside
 *  closes it. The line is the button's description (aria-describedby), so a screen reader reads it too. */
export function helpTip(key) {
  const id = `tip-${++tipSeq}`;
  const tip = h("span", { class: "tip", role: "tooltip", id, hidden: true }, t(`help.${key}`));
  const btn = h("button", { class: "info-btn", type: "button", "aria-label": t("help.button", { word: t(`word.${key}`) }),
    "aria-describedby": id, "aria-expanded": "false", "data-help": key }, "ⓘ");
  let pinned = false;
  const show = (on) => {
    tip.hidden = !on;
    btn.setAttribute("aria-expanded", String(on));
    if (on) { closeTips(close); openTips.add(close); } else { pinned = false; openTips.delete(close); }
  };
  const close = () => show(false);
  btn.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); pinned = !pinned || tip.hidden; show(pinned); });
  btn.addEventListener("mouseenter", () => show(true));
  btn.addEventListener("mouseleave", () => { if (!pinned) show(false); });
  btn.addEventListener("focus", () => show(true));
  btn.addEventListener("blur", () => { if (!pinned) show(false); });
  return h("span", { class: "info" }, btn, tip);
}

/** A time like "2:12" (or "0:00–2:12") as text with its meaning on hover; anything else as plain text. */
export function timeText(text, attrs = {}) {
  return h("span", { ...attrs, title: timeTitle(text) }, text);
}

// ---------- copy ----------

export function copyButton(text, label = t("common.copy")) {
  const btn = h("button", { class: "btn sm", type: "button" }, icon("copy"), h("span", {}, label));
  const word = btn.querySelector("span");
  btn.addEventListener("click", async () => {
    let ok = false;
    try {
      await navigator.clipboard.writeText(text);
      ok = true;
    } catch {
      const ta = h("textarea", { style: "position:fixed;opacity:0" }, text);
      document.body.append(ta);
      ta.select();
      try { ok = document.execCommand("copy"); } catch { ok = false; }
      ta.remove();
    }
    word.textContent = ok ? t("common.copied") : t("common.copy_failed");
    btn.classList.toggle("copied", ok);
    setTimeout(() => { word.textContent = label; btn.classList.remove("copied"); }, 1400);
  });
  return btn;
}

// ---------- dialog ----------

/** A modal dialog. html: string (trusted markup) or Node. actions: [{label, primary, onClick(close), keepOpen}]. */
export function dialog(name, html, actions = [], opts = {}) {
  const before = document.activeElement;
  const titleId = `dlg-${Math.random().toString(36).slice(2)}`;
  const body = h("div", { class: "db" });
  if (html instanceof Node) body.append(html); else body.innerHTML = html || "";
  const el = h("dialog", { class: `dlg${opts.wide ? " wide" : ""}`, "aria-labelledby": titleId, "data-dialog": name });
  const close = () => { if (el.open) el.close(); };
  el.addEventListener("close", () => { el.remove(); if (before && before.focus) before.focus(); });
  el.addEventListener("click", (e) => { if (e.target === el) close(); });  // click on the backdrop
  const foot = h("div", { class: "df" });
  for (const a of actions) {
    foot.append(h("button", {
      class: `btn${a.primary ? " pri" : ""}`, type: "button",
      onclick: async () => { if (a.onClick) await a.onClick(close, el); if (!a.keepOpen) close(); },
    }, a.label));
  }
  el.append(
    h("div", { class: "dh" }, opts.head || null, h("h2", { id: titleId }, opts.title || name),
      h("button", { class: "x", type: "button", "aria-label": t("common.close"), onclick: close }, icon("x"))),
    body, actions.length ? foot : null);
  document.body.append(el);
  el.showModal();
  return { el, close };
}

// ---------- uploads ----------

function ext(name) {
  const i = name.lastIndexOf(".");
  return i < 0 ? "" : name.slice(i + 1).toLowerCase();
}

/** Plain-words problem with a file for this kind, or "" when it may be sent. The server closes early on 413/415. */
export function uploadProblem(kind, file) {
  const rule = UPLOAD_RULES[kind];
  if (!rule) return t("upload.kind");
  if (!rule.exts.includes(ext(file.name))) return t("upload.type", { name: file.name, types: rule.exts.join(", ") });
  if (file.size > rule.limit) return t("upload.big", { name: file.name, limit: rule.limitText });
  if (file.size === 0) return t("upload.empty", { name: file.name });
  return "";
}

/** A drop zone that copies files into the video folder (refs/, storyboard/, vo/, music/). opts: {id, label, multiple, onDone} */
export function dropZone(kind, ctx, opts = {}) {
  const rule = UPLOAD_RULES[kind] || { exts: [], where: "" };
  const multiple = opts.multiple ?? kind !== "keyframe";
  const types = rule.exts.map((e) => e.toUpperCase()).join(", ");
  const input = h("input", { type: "file", class: "sr", tabindex: "-1", "aria-hidden": "true",
    accept: rule.exts.map((e) => "." + e).join(","), multiple });
  const status = h("div", { class: "msg", role: "status" });
  const zone = h("div", { class: "drop", role: "button", tabindex: "0",
    "aria-label": t("upload.zone_label", { label: opts.label || t("upload.add_files") }) },
  h("b", {}, opts.label || t("upload.drop_files")), t("upload.or_click"), h("br"),
  // a picture for one card says whose picture it becomes ("Shot 5", the character's name), never storyboard/SB-5.png
  opts.id ? h("span", { class: "hint", title: `${rule.where}${opts.id}` }, t("upload.pic_to", { types, name: label(opts.id, ctx.data) }))
    : h("span", { class: "hint" }, t("upload.copied_to", { types }), " ", h("span", { class: "mono" }, rule.where)),
  input, status);

  const send = async (files) => {
    const list = [...files].slice(0, multiple ? undefined : 1);
    for (const file of list) {
      const problem = uploadProblem(kind, file);
      if (problem) { status.className = "msg err"; status.textContent = problem; continue; }
      const bar = h("i", { style: "width:0%" });
      status.className = "msg";
      status.replaceChildren(t("upload.copying", { name: file.name }), h("div", { class: "bar" }, bar));
      try {
        const q = { folder: ctx.folder, kind, name: file.name };
        if (opts.id) q.id = opts.id;
        const res = await ctx.upload(q, file, (f) => { bar.style.width = `${Math.round(f * 100)}%`; });
        status.className = "msg ok";
        status.textContent = opts.id ? t("upload.pic_saved", { name: label(opts.id, ctx.data) }) : t("upload.saved", { name: file.name });
        if (opts.onDone) opts.onDone(res);
      } catch (e) {
        status.className = "msg err";
        status.textContent = e.message || t("upload.not_finished");
      }
    }
  };
  zone.addEventListener("click", (e) => { if (e.target !== input) input.click(); });
  zone.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
  input.addEventListener("change", () => { send(input.files); input.value = ""; });
  zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("over"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("over"));
  zone.addEventListener("drop", (e) => { e.preventDefault(); zone.classList.remove("over"); send(e.dataTransfer.files); });
  return zone;
}

// ---------- gate bar ----------

const sentLocal = new Map();  // `${folder}|${gate}|${question}` -> {value}, between POST and the next poll

/** {value} of the editor's answer to this question of this gate (from the inbox, or just sent), else null. */
function answered(ctx, gate, q) {
  const local = sentLocal.get(`${ctx.folder}|${gate.id}|${q.id}`);
  if (local) return local;
  const ev = [...(ctx.data?.events || [])].reverse()
    .find((e) => e.type === "answer" && e.gate === gate.id && e.target === q.id && !e.stale);
  return ev ? { value: ev.value } : null;
}

/** The checklist and approval confirms have no control of their own: Proceed is the yes, and anything missing or to
 *  change goes in the note box. Every other yes/no question is a real decision: Yes / No radio buttons. A confirm
 *  that is an instruction ("Please quit CapCut…", "It's saved") is a line to read; Proceed says it's done. */
const APPROVALS = new Set(["checklist", "approve", "approve_ok"]);
const isYesNo = (q) => q.kind === "confirm" && APPROVALS.has(q.id);
// a question mark anywhere makes it a question ("…made? (Recommended for new clients.)" still asks Yes / No)
const isInstruction = (q, label) => q.kind === "confirm" && (label?.no === null || !String(q.text || "").includes("?"));

/** "Pick the graphics": one or more templates of a few (more than one = different styles to try), as cards with the
 *  template's preview still, its name and what it's for. options [{value: template name (or "auto" = let Claude
 *  choose), label, desc?, suggested?, why?}]; `suggested` cards carry a badge (`why`: e.g. popular on Prompt Motion).
 *  "Let Claude choose" and the templates exclude each other. Claude's pick(s) (`default`, a name or a list) start
 *  checked; nothing sends until Proceed, which sends the list. */
function templateCards(name, q) {
  const opts = (q.options || []).map((o) => (typeof o === "object" && o !== null ? o : { value: o, label: String(o) }));
  const picked = Array.isArray(q.default) ? q.default : q.default === undefined ? [] : [q.default];
  const inputs = [];
  const node = h("div", { class: "tcards", role: "group", "aria-label": q.text }, opts.map((o) => {
    const auto = o.value === "auto";
    const input = h("input", { type: "checkbox", name, value: String(o.value), checked: picked.includes(o.value), class: "sr",
      onchange: () => {  // Let Claude choose, or your own picks: not both
        if (!input.checked) return;
        inputs.forEach((x, i) => { if (x !== input && (auto || opts[i].value === "auto")) x.checked = false; });
      } });
    inputs.push(input);
    const why = o.suggested ? String(o.why || t("gate.gfx_suggested_why")) : "";
    return h("label", { class: `tcard${auto ? " auto" : ""}${o.suggested ? " suggested" : ""}`, title: why || null }, input,
      o.suggested ? h("span", { class: "tbadge" }, `★ ${t("gate.gfx_suggested")}`) : null,
      auto ? h("div", { class: "tthumb auto" }, "✦")
        : h("img", { class: "tthumb", src: `/api/template-preview?name=${encodeURIComponent(String(o.value))}`, alt: "",
          loading: "lazy", onerror: (e) => { e.target.replaceWith(h("div", { class: "tthumb none" }, String(o.label || o.value))); } }),
      h("b", {}, String(o.label || o.value)), o.desc ? h("span", { class: "hint" }, String(o.desc)) : null,
      why ? h("span", { class: "twhy" }, why) : null);
  }));
  // a look from prompt-motion.com (or any page): its link goes in the list; Claude has it built as a new template
  const link = h("input", { type: "url", class: "f tlink", placeholder: "https://prompt-motion.com/…", "aria-label": t("gate.gfx_link") });
  const value = () => {
    const v = opts.filter((o, i) => inputs[i].checked).map((o) => o.value);
    const url = link.value.trim();
    if (/^https?:\/\/\S+$/i.test(url)) v.push(url);
    return v.length ? v : undefined;
  };
  return { node: h("div", {}, h("p", { class: "hint tnote" }, t("gate.gfx_many")), node,
    h("label", { class: "tlink-row" }, h("span", {}, t("gate.gfx_link")), link, h("span", { class: "hint" }, t("gate.gfx_link_hint")))),
  value, lock: () => { inputs.forEach((x) => { x.disabled = true; }); link.disabled = true; } };
}

/** One-of-many as radio buttons (nothing sends until Proceed); `picked` starts selected. */
function radios(name, options, picked) {
  const inputs = options.map((o) => h("input", { type: "radio", name, value: JSON.stringify(o.value),
    checked: picked !== undefined && o.value === picked }));
  const node = h("div", { class: "radios", role: "radiogroup" },
    ...options.map((o, i) => h("label", { class: "check" }, inputs[i], o.label)));
  const value = () => { const i = inputs.findIndex((x) => x.checked); return i < 0 ? undefined : options[i].value; };
  return { node, value, lock: () => inputs.forEach((x) => { x.disabled = true; }) };
}
/** Claude's own "What should change?" (id `changes`) is the note box: it isn't shown twice, and gets the note's text. */
const isChanges = (q) => q.kind === "text" && q.id === "changes";

/** One question's field: {node, value() -> value | undefined (nothing picked), lock()}. Nothing is sent from here. */
function questionField(gate, q, ctx, label) {
  const box = h("div", { class: "opts" });
  const options = (q.options || []).map((o) => (typeof o === "object" && o !== null
    ? { value: o.value ?? o.id ?? o.label, label: o.label ?? String(o.value ?? o.id) } : { value: o, label: String(o) }));
  const name = `gate-${gate.id}-${q.id}`;
  if (q.kind === "choice") return radios(name, options, q.default);  // one of many; Claude's suggestion starts picked
  if (q.kind === "cards") return templateCards(name, q);
  if (q.kind === "confirm" && !isYesNo(q) && !isInstruction(q, label)) {  // a real yes/no decision
    return radios(name, [{ value: true, label: label?.yes || t("common.yes") }, { value: false, label: label?.no || t("common.no") }],
      q.default);
  }
  if (q.kind === "multi") {
    const defaults = Array.isArray(q.default) ? q.default : [];
    const checks = options.map((o) => h("input", { type: "checkbox", value: String(o.value), checked: defaults.includes(o.value),
      "data-key": `gate:${gate.id}:${q.id}:${o.value}` }));
    box.append(...options.map((o, i) => h("label", { class: "check" }, checks[i], o.label)));
    return { node: box, value: () => options.filter((o, i) => checks[i].checked).map((o) => o.value),
      lock: () => checks.forEach((c) => { c.disabled = true; }) };
  }
  if (q.kind === "text") {
    const ta = h("textarea", { class: "f", rows: 2, "data-key": `gate:${gate.id}:${q.id}`, "aria-label": q.text },
      typeof q.default === "string" ? q.default : "");
    box.style.display = "block";
    box.append(ta);
    return { node: box, value: () => ta.value.trim(), lock: () => { ta.disabled = true; } };  // optional: "" is none
  }
  if (q.kind === "file") {  // the file is copied as it drops; Proceed sends its path
    const [kind, id] = fileTarget(gate.step, q);
    let saved;
    box.style.display = "block";
    const picked = h("ul", { class: "files" });
    const zone = dropZone(kind, ctx, { label: t("gate.drop_file"), id, onDone: (res) => {
      saved = res.path;
      skip.checked = false;
      if (kind === "keyframe") return;  // a picture for a card is replaced by dropping another, not removed
      const name = String(res.path).split(/[\/]/).pop();
      const x = h("button", { class: "file-x", type: "button", "aria-label": t("upload.remove", { name }), title: t("upload.remove", { name }) }, "×");
      x.addEventListener("click", async () => {  // out of the video (into .edit-mo-to/removed/), and Claude is told
        x.disabled = true;
        try {
          await ctx.api("/api/upload-remove", { body: { folder: ctx.folder, path: res.path } });
          x.closest("li")?.remove();
          if (saved === res.path) saved = undefined;
        } catch (e) {
          x.disabled = false;
          toast(e.message || t("common.not_sent"));
        }
      });
      picked.append(h("li", { title: res.path }, h("span", { class: "mono" }, name), x));
    } });
    // no file at all (e.g. a video with no voiceover): the answer is "skip"; Claude's `skip` names the choice
    const skip = h("input", { type: "checkbox", onchange: () => { zone.classList.toggle("off", skip.checked); } });
    box.append(zone, picked, h("label", { class: "check file-skip" }, skip, String(q.skip || t("gate.file_skip"))));
    return { node: box, value: () => (skip.checked ? "skip" : saved),
      lock: () => { zone.remove(); skip.disabled = true; } };
  }
  return { node: null, value: () => true, lock: () => {} };  // confirm: Proceed is the yes
}

/** The question bar: Claude's message, every question as a field (a yes/no question has none), the page's own extra
 *  questions (`extra`: {target, questions: [{id, text, why}]}, e.g. the brief's questions, sent as one answer; and
 *  `extra.before()`: the page's own edits sent first, e.g. the script lines changed in the table; `notesLabel`,
 *  `notesPh`, `notesRequired`: the note box renamed, e.g. Review's "What should change?"), one
 *  "Anything to add or change?" box (answer target "notes") and one Proceed that sends it all. */
/** Questions already brought into view once (`${folder}|${gate id}`): a redraw never scrolls the page again. */
const spotlit = new Set();
/** Questions reopened with "Change my answer": `${folder}|${gate id}`. */
const changing = new Set();

/** Reopen a question's sent answers for changing (the loading card's Change my answer). */
export function reopenGate(folder, gateId) {
  changing.add(`${folder}|${gateId}`);
}

/** The answers this gate has in the inbox (not stale), and whether Claude has picked them all up (handled). */
function gateAnswers(ctx, gate) {
  const evs = (ctx.data?.events || []).filter((e) => e.type === "answer" && e.gate === gate.id && !e.stale);
  const handled = new Set(ctx.data?.job?.handled || []);
  return { evs, handled: evs.length > 0 && evs.every((e) => handled.has(e.seq)) };
}

export function gateBar(gate, ctx, labels = {}, extra = null) {
  const bar = h("section", { class: "gatebar", "aria-label": t("gate.waiting") });
  bar.append(h("div", { class: "gh" }, h("div", { class: "ic", "aria-hidden": "true" }, "!"),
    h("div", {}, h("b", {}, t("gate.waiting_title", { title: gate.title }), helpTip("question")), gate.detail ? h("span", {}, gate.detail) : null)));
  const key = `${ctx.folder}|${gate.id}`;
  const qs = gate.questions || [];
  const lastNotes = [...gateAnswers(ctx, gate).evs].reverse().find((e) => e.target === "notes");
  const notes = h("textarea", { class: "f", rows: 3, id: `gate-notes-${gate.id}`, "data-key": `gate:${gate.id}:notes`,
    placeholder: extra?.notesPh || t("gate.notes_ph") }, typeof lastNotes?.value === "string" ? lastNotes.value : "");
  // every part the editor answers, in order: {node, check() -> what's missing | null}
  const parts = [];
  const fields = qs.map((q) => {
    // "Quit CapCut": the page's red reminder says it; Proceed is the "it's closed" (checked first, below)
    if (q.id === "capcut_closed") return { q, f: { node: null, value: () => true, lock: () => {} } };
    const f = isChanges(q) ? { node: null, value: () => notes.value.trim(), lock: () => {} }
      // a previous answer (Change my answer) starts picked / filled in
      : questionField(gate, { ...q, default: answered(ctx, gate, q)?.value ?? q.default }, ctx, labels[q.id]);
    if (!isYesNo(q) && !isChanges(q)) {
      parts.push({ node: h("div", { class: "gq" }, h("div", { class: "qt" }, labels[q.id]?.text || q.text),
        q.why ? h("div", { class: "why" }, q.why) : null, f.node),
      check: () => (f.node && f.value() === undefined ? q.text : null) });
    }
    return { q, f };
  });
  const extraBoxes = (extra?.questions || []).map((x) => {
    const ta = h("textarea", { class: "f", rows: 2, "data-key": `gate:${gate.id}:x:${x.id}`, "aria-label": x.text });
    parts.push({ node: h("div", { class: "gq" }, h("div", { class: "qt" }, x.text), x.why ? h("div", { class: "why" }, x.why) : null, ta),
      check: () => null });
    return { x, ta };
  });
  const notesLabel = extra?.notesLabel || t("gate.notes");
  const notesPart = { node: h("div", { class: "gq" }, h("label", { class: "qt", for: notes.id }, notesLabel), notes),
    check: () => (extra?.notesRequired && !notes.value.trim() ? notesLabel : null) };
  if (extra?.notesFirst) parts.unshift(notesPart); else parts.push(notesPart);
  const progress = h("div", { class: "gstep", "aria-live": "polite" });
  bar.append(progress, ...parts.map((x) => x.node));
  const msg = h("div", { class: "msg", role: "status" });
  const btn = h("button", { class: "btn pri", type: "button" }, t("gate.proceed"));
  const back = h("button", { class: "btn", type: "button" }, t("gate.back"));
  const next = h("button", { class: "btn pri", type: "button" }, t("gate.next"));
  const nav = h("div", { class: "row gnav", style: "margin-top:12px" }, back, next, btn);
  bar.append(nav, msg);

  const lockAll = (text, cls) => {
    fields.forEach(({ f }) => f.lock());
    extraBoxes.forEach(({ ta }) => { ta.disabled = true; });
    notes.disabled = true;
    btn.disabled = true;
    msg.className = cls;
    msg.textContent = text;
  };
  const sent = qs.length && qs.every((q) => answered(ctx, gate, q));
  const locked = sent && !changing.has(key);
  // three or more parts: one at a time (Question n of N, Back, Next), Proceed on the last; fewer: all at once
  const wizard = !locked && parts.length >= 3;
  let at = 0;
  const show = () => {
    parts.forEach((x, i) => { x.node.hidden = wizard && i !== at; });
    progress.hidden = !wizard;
    progress.textContent = wizard ? t("gate.step_of", { n: at + 1, total: parts.length }) : "";
    back.hidden = !wizard || at === 0;
    next.hidden = !wizard || at === parts.length - 1;
    btn.hidden = wizard && at !== parts.length - 1;
  };
  back.addEventListener("click", () => { at = Math.max(0, at - 1); msg.textContent = ""; show(); });
  next.addEventListener("click", () => {
    const missing = parts[at].check();
    if (missing) { msg.className = "msg err"; msg.textContent = t("gate.answer_first", { question: missing }); return; }
    msg.textContent = "";
    at += 1;
    show();
    parts[at].node.querySelector("textarea, input")?.focus();
  });
  show();
  if (!locked) {  // the editor's turn: the bar glows, and the first time this question shows the page brings it into view
    bar.classList.add("attention");
    if (!spotlit.has(key)) {
      setTimeout(() => {
        if (!bar.isConnected || spotlit.has(key)) return;  // a redraw replaced it: the new bar does this
        spotlit.add(key);
        bar.scrollIntoView({ block: "center" });  // instant: a smooth scroll is skipped by some browsers
        // the first thing to answer: a choice, a box to type in, or the drop box (never the hidden file picker)
        bar.querySelector(".drop, input:not([type=hidden]):not([type=file]):not(.sr):not([disabled]), textarea:not([disabled]), select")
          ?.focus({ preventScroll: true });
      }, 350);
    }
  }
  if (locked) {
    const stale = qs.some((q) => answered(ctx, gate, q)?.stale);
    lockAll(stale ? staleText() : t("gate.sent"), stale ? "msg err" : "msg ok");
    if (!stale) {  // until Claude picks them up the answers can still change; after that, tell Claude in the panel
      bar.append(gateAnswers(ctx, gate).handled
        ? h("p", { class: "hint gate-after" }, t("gate.too_late"))
        : h("button", { class: "linkish gate-after", type: "button", onclick: () => {
          changing.add(key);
          bar.replaceWith(gateBar(gate, ctx, labels, extra));
        } }, t("gate.change")));
    }
    return bar;
  }
  btn.addEventListener("click", async () => {
    const gap = parts.findIndex((x) => x.check());  // e.g. Review's "What should change?" left empty
    if (gap >= 0) {
      msg.className = "msg err";
      msg.textContent = t("gate.answer_first", { question: parts[gap].check() });
      if (wizard) { at = gap; show(); }
      return;
    }
    if (qs.some((q) => q.id === "capcut_closed")) {  // Claude writes to the project next: CapCut must be closed
      btn.disabled = true;
      const running = await ctx.api("/api/capcut").then((r) => Boolean(r?.running)).catch(() => false);
      btn.disabled = false;
      if (running) {
        msg.className = "msg err";
        msg.textContent = t("gate.capcut_running");
        ctx.openDialog?.("capcut", { onClosed: () => { msg.textContent = ""; btn.click(); }, onCancel: () => {} });
        return;
      }
    }
    btn.disabled = true;
    const send = (target, value) => ctx.send({ type: "answer", step: gate.step || null, gate: gate.id, target, value });
    try {
      if (extra?.before) await extra.before();
      const answers = {};
      for (const { x, ta } of extraBoxes) if (ta.value.trim()) answers[x.id] = ta.value.trim();
      if (extra && Object.keys(answers).length) await send(extra.target, answers);
      if (notes.value.trim() && !qs.some(isChanges)) await send("notes", notes.value.trim());
      let stale = false;
      for (const { q, f } of fields) {  // the questions last: once they're all in, Claude carries on
        const ev = await send(q.id, f.value());
        stale = stale || Boolean(ev?.stale);
        sentLocal.set(`${ctx.folder}|${gate.id}|${q.id}`, { value: f.value(), stale: Boolean(ev?.stale) });
      }
      changing.delete(key);
      bar.replaceWith(gateBar(gate, ctx, labels, extra));  // the sent view, with Change my answer
      if (stale) lockAll(staleText(), "msg err");
    } catch (e) {
      btn.disabled = false;
      msg.className = "msg err";
      msg.textContent = e.message || t("common.not_sent");
    }
  });
  return bar;
}

// ---------- setup check ----------

/** The /api/checks rows [{name, ok, detail}] as a table; extra: [[label, Node]] rows appended. */
export function checksTable(checks, extra = []) {
  const rows = (checks || []).map((c) => h("tr", {},
    h("td", {}, c.name, c.detail ? h("div", { class: "note" }, c.detail) : null),
    h("td", { style: "text-align:right" }, chip(t(c.ok ? "checks.ok" : "checks.missing"), c.ok ? "ok" : "err"))));
  for (const [label, node] of extra) rows.push(h("tr", {}, h("td", {}, label), h("td", { style: "text-align:right" }, node)));
  return h("table", {}, h("tbody", {}, rows));
}

// ---------- table ----------

const STATUS_KEYS = ["ok", "wait", "you", "err", "opt", "mute"];  // words: WORDS.status.<status>
const TIME = /^\d+:\d{2}(:\d{2})?(\s*[–-]\s*\d+:\d{2}(:\d{2})?)?$/;

/** The generic table {title, columns, rows: [{id, cells, status, note}]}. opts: {words, actions(row) -> Node} */
export function table(tb, ctx, opts = {}) {
  const words = { ...Object.fromEntries(STATUS_KEYS.map((k) => [k, t(`status.${k}`)])), ...(opts.words || {}) };
  const rows = tb?.rows || [];
  const hasStatus = rows.some((r) => r.status);
  const counts = {};
  rows.forEach((r) => { if (r.status) counts[r.status] = (counts[r.status] || 0) + 1; });
  const head = h("div", { class: "row spread", style: "margin-bottom:8px" }, h("h3", { style: "margin:0" }, tb?.title || ""),
    h("div", { class: "row" }, Object.entries(counts).map(([s, n]) => chip(`${n} ${words[s] || s}`, s))));
  const thead = h("tr", {}, (tb?.columns || []).map((c) => h("th", { scope: "col" }, c)),
    hasStatus ? h("th", { scope: "col" }, t("table.status")) : null, opts.actions ? h("th", {}, h("span", { class: "sr" }, t("table.actions"))) : null);
  const body = rows.map((r) => h("tr", { "data-id": r.id },
    (r.cells || []).map((c, i) => h("td", { class: TIME.test(c) ? "mono" : null, title: TIME.test(c) ? timeTitle(c) : null }, c,
      i === 0 && r.note ? h("div", { class: "note" }, r.note) : null)),
    hasStatus ? h("td", {}, r.status ? chip(words[r.status] || r.status, r.status) : null) : null,
    opts.actions ? h("td", {}, opts.actions(r) || null) : null));
  return h("section", { class: "card" }, head,
    h("div", { class: "tablewrap" }, h("table", {}, h("thead", {}, thead), h("tbody", {}, body))),
    rows.length ? null : h("p", { class: "hint" }, t("table.empty")));
}
