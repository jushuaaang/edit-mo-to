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

import { t, timeTitle } from "./words.js";

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
  const input = h("input", { type: "file", class: "sr", tabindex: "-1", "aria-hidden": "true",
    accept: rule.exts.map((e) => "." + e).join(","), multiple });
  const status = h("div", { class: "msg", role: "status" });
  const zone = h("div", { class: "drop", role: "button", tabindex: "0",
    "aria-label": t("upload.zone_label", { label: opts.label || t("upload.add_files") }) },
  h("b", {}, opts.label || t("upload.drop_files")), t("upload.or_click"), h("br"),
  h("span", { class: "hint" }, t("upload.copied_to", { types: rule.exts.map((e) => e.toUpperCase()).join(", ") }), " ",
    h("span", { class: "mono" }, opts.id ? `${rule.where}${opts.id}.png` : rule.where)),
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
        status.textContent = t("upload.saved", { name: file.name });
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

function answerText(value, file = false) {
  if (value === true) return t("common.yes");
  if (value === false) return t("common.no");
  if (Array.isArray(value)) return value.length ? value.join(", ") : t("common.none");
  const s = String(value ?? "");
  return file ? s.split(/[\\/]/).pop() : s;  // a file answer is a path: show its name
}

function questionControls(gate, q, ctx, done, label) {
  const box = h("div", { class: "opts" });
  const answer = async (value, controls) => {
    controls.forEach((c) => { c.disabled = true; });
    try {
      const ev = await ctx.send({ type: "answer", step: gate.step || null, gate: gate.id, target: q.id, value });
      if (ev?.stale) { done({ value, stale: true }); return true; }  // the gate changed before the click
      sentLocal.set(`${ctx.folder}|${gate.id}|${q.id}`, { value });
      done({ value });
      return true;
    } catch (e) {
      controls.forEach((c) => { c.disabled = false; });
      toast(e.message || t("common.not_sent"));
      return false;
    }
  };
  const options = (q.options || []).map((o) => (typeof o === "object" && o !== null
    ? { value: o.value ?? o.id ?? o.label, label: o.label ?? String(o.value ?? o.id) } : { value: o, label: String(o) }));

  if (q.kind === "choice") {
    const btns = options.map((o) => h("button", {
      class: `btn${o.value === q.default ? " pri" : ""}`, type: "button", "data-value": JSON.stringify(o.value),
      onclick: () => answer(o.value, btns),
    }, o.label));
    box.append(...btns);
  } else if (q.kind === "confirm") {
    // a page may relabel a confirm (labels: {yes, no}); no: null drops the No button (the storyboard's "It's saved")
    const btns = [
      h("button", { class: "btn pri", type: "button", "data-value": "true", onclick: () => answer(true, btns) }, label?.yes || t("common.yes")),
      label?.no === null ? null
        : h("button", { class: "btn", type: "button", "data-value": "false", onclick: () => answer(false, btns) }, label?.no || t("common.no")),
    ].filter(Boolean);
    box.append(...btns);
  } else if (q.kind === "multi") {
    const defaults = Array.isArray(q.default) ? q.default : [];
    const checks = options.map((o) => h("input", { type: "checkbox", value: String(o.value), checked: defaults.includes(o.value),
      "data-key": `gate:${gate.id}:${q.id}:${o.value}` }));
    const sendBtn = h("button", { class: "btn pri", type: "button" }, t("common.send"));
    sendBtn.addEventListener("click", () => answer(
      options.filter((o, i) => checks[i].checked).map((o) => o.value), [...checks, sendBtn]));
    box.append(...options.map((o, i) => h("label", { class: "check" }, checks[i], o.label)), sendBtn);
  } else if (q.kind === "text") {
    const ta = h("textarea", { class: "f", rows: 2, "data-key": `gate:${gate.id}:${q.id}`, "aria-label": q.text },
      typeof q.default === "string" ? q.default : "");
    const sendBtn = h("button", { class: "btn pri", type: "button" }, t("common.send"));
    const go = () => { if (ta.value.trim()) answer(ta.value.trim(), [ta, sendBtn]); else ta.focus(); };
    sendBtn.addEventListener("click", go);
    ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); go(); } });
    box.style.flexDirection = "column";
    box.style.alignItems = "flex-start";
    box.append(ta, sendBtn);
  } else if (q.kind === "file") {
    const [kind, id] = fileTarget(gate.step, q);
    let saved = null;  // the uploaded path: a failed answer is sent again without uploading again
    const retry = h("button", { class: "btn sm pri", type: "button", hidden: true }, t("gate.send_again"));
    const sendPath = async () => { retry.hidden = await answer(saved, [retry]); };
    retry.addEventListener("click", sendPath);
    box.style.display = "block";
    box.append(dropZone(kind, ctx, { label: t("gate.drop_file"), id, onDone: (res) => { saved = res.path; sendPath(); } }),
      retry);
  }
  return box;
}

/** "Waiting on you: …" with every question of the open gate; each answer is an `answer` event. */
export function gateBar(gate, ctx, labels = {}) {
  const bar = h("section", { class: "gatebar", "aria-label": t("gate.waiting") });
  bar.append(h("div", { class: "gh" }, h("div", { class: "ic", "aria-hidden": "true" }, "!"),
    h("div", {}, h("b", {}, t("gate.waiting_title", { title: gate.title }), helpTip("question")), gate.detail ? h("span", {}, gate.detail) : null)));
  for (const q of gate.questions || []) {
    const wrap = h("div", { class: "gq" }, h("div", { class: "qt" }, q.text), q.why ? h("div", { class: "why" }, q.why) : null);
    const showSent = (ans) => {
      wrap.querySelectorAll("button, input, textarea, select").forEach((c) => { c.disabled = true; });
      wrap.querySelectorAll(".drop").forEach((d) => d.remove());
      wrap.querySelectorAll(".opts .btn").forEach((b) => {  // mark the answer given, not the default
        const picked = b.dataset.value === JSON.stringify(ans.value);
        b.classList.toggle("pri", picked);
        b.setAttribute("aria-pressed", String(picked));
      });
      if (Array.isArray(ans.value)) {
        wrap.querySelectorAll(".opts input[type=checkbox]").forEach((c) => { c.checked = ans.value.map(String).includes(c.value); });
      }
      if (!wrap.querySelector(".sent")) {
        wrap.append(h("div", { class: "sent row" },
          ans.stale ? chip(staleText(), "err") : chip(t("common.sent_waiting"), "wait"),
          h("span", { class: "hint" }, t(ans.stale ? "gate.not_counted" : "gate.your_answer",
            { answer: answerText(ans.value, q.kind === "file") }))));
      }
    };
    wrap.append(questionControls(gate, q, ctx, showSent, labels[q.id]));
    const ans = answered(ctx, gate, q);
    if (ans) showSent(ans);
    bar.append(wrap);
  }
  return bar;
}

// ---------- ask box ----------

const TAG = /^\s*\[([a-z]+)\]\s*/;

/** Claude's log lines for a step: entries with step === step, or text starting with "[step] ". */
export function logForStep(log, step) {
  return (log || []).flatMap((e) => {
    const m = TAG.exec(e.text || "");
    if (e.step === step) return [{ ...e, text: m ? e.text.slice(m[0].length) : e.text }];
    if (m && m[1] === step) return [{ ...e, text: e.text.slice(m[0].length) }];
    return [];
  });
}

/** "Tell Claude about this step": that step's messages and Claude's step-tagged log lines, then a box. */
export function askBox(step, data, ctx) {
  const mine = (data?.events || []).filter((e) => e.type === "message" && e.step === step)
    .map((e) => ({ at: e.at, text: e.text, me: true }));
  const claude = logForStep(data?.job?.log, step).map((e) => ({ at: e.at, text: e.text, me: false }));
  const items = [...mine, ...claude].sort((a, b) => Date.parse(a.at) - Date.parse(b.at)).slice(-12);
  const hist = h("ol", { class: "hist", "aria-label": t("ask.history") },
    items.map((it) => h("li", { class: it.me ? "me" : "cl" }, it.me ? it.text : t("ask.claude_says", { text: it.text }),
      h("small", {}, it.me ? t("ask.you_at", { when: relTime(it.at) }) : relTime(it.at)))));
  const id = `ask-${step}`;
  const ta = h("textarea", { class: "f", id, rows: 2, "data-key": `ask:${step}`,
    placeholder: t("ask.placeholder", { step: stepTitle(step).toLowerCase() }) });
  const note = h("div", { class: "msg", role: "status" });
  const btn = h("button", { class: "btn sm pri", type: "button" }, t("common.send"));
  const go = async () => {
    const text = ta.value.trim();
    if (!text) { ta.focus(); return; }
    btn.disabled = true;
    try {
      await ctx.send({ type: "message", step, text });
      ta.value = "";
      note.className = "msg ok";
      note.textContent = t(data?.listening ? "common.sent_listening" : "common.saved_later");
    } catch (e) {
      note.className = "msg err";
      note.textContent = e.message || t("common.not_sent");
    } finally {
      btn.disabled = false;
    }
  };
  btn.addEventListener("click", go);
  ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); go(); } });
  return h("section", { class: "ask", "aria-labelledby": `${id}-h` },
    h("div", { class: "ah" }, h("span", { class: `pulse${data?.listening ? "" : " off"}`, "aria-hidden": "true" }),
      h("b", { id: `${id}-h` }, t("ask.title")), h("span", {}, t("ask.sub", { step: stepTitle(step) }))),
    items.length ? hist : null,
    h("label", { class: "sr", for: id }, t("ask.label", { step: stepTitle(step) })), ta,
    h("div", { class: "row spread", style: "margin-top:8px" }, h("span", { class: "hint" }, t("ask.ctrl_enter")), btn),
    note);
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
