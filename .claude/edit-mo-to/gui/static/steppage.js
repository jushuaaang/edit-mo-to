// The frame every step page shares (pages/<step>.js), and the inputs pages put in it.
//
// stepPage(root, step, data, ctx, parts) draws: the "what to do now" strip, crumbs and title with "why this step" and
// a time guess, the "You" line for steps the editor does
// outside the app, the gate bar, the CapCut banner, then
//   - the step's content (parts.body) once Claude has started the step;
//   - only its early inputs (parts.early) while it is not started and takes early input (data.early);
//   - otherwise "Waits for: <previous step>";
// and the "Tell Claude about this step" box at the bottom.
//
// Inputs are inbox events: an `answer` with target "<step>:<id>" and gate null ("early": true while the step is
// not started), an `upload`, or an `action` for buttons that change files (Claude acts on them). Every string from
// job data, the inbox, outputs or file names reaches the DOM as text through h().
import { h, chip, stepChip, gateBar, askBox, table, pendingChip, toast, dropZone, copyButton, stepTitle, previousStep,
  STEPS, STALE_TEXT } from "./ui.js";
import { t } from "./words.js";
import { nowStrip } from "./nextstep.js";

export const CAPCUT_Q = "capcut_closed";
const NOT_LISTENING = "Claude isn't listening. Your answer is saved; it's picked up when Claude next checks, or type 'go' in chat.";

// ---------- reading the job ----------

export const stateOf = (data, step) => data?.job?.steps?.[step]?.state || "pending";
export const openGate = (data, step) => (data?.job?.gate?.step === step ? data.job.gate : null);
export const outputsOf = (data, step) => data?.outputs?.[step] || {};
export const isTable = (o) => Boolean(o) && Array.isArray(o.columns) && Array.isArray(o.rows);
export const card = (data) => data?.job?.card || {};
export const timelines = (data) => (Array.isArray(card(data).timelines) ? card(data).timelines : []);
export const baseName = (p) => String(p ?? "").split(/[\\/]/).pop();
const handled = (data) => new Set(data?.job?.handled || []);

/** Latest answer or upload for an input target ("<step>:<id>"); the latest one wins. */
export function lastInput(data, target) {
  return [...(data?.events || [])].reverse()
    .find((e) => (e.type === "answer" || e.type === "upload") && e.target === target && !e.stale) || null;
}

/** Editor events Claude has not handled yet (edit / approve / action) for a target. */
export const pendingFor = (data, target) => (data?.pending || []).filter((e) => e.target === target);

/** Does the open gate of this step ask question `id`? Then the gate bar asks it, not the page. */
export const gateAsks = (data, step, id) => Boolean(openGate(data, step)?.questions?.some((q) => q.id === id));

/** The editor's non-stale answer to a question of the open gate, or null. */
export function gateAnswer(data, gate, qid) {
  return [...(data?.events || [])].reverse()
    .find((e) => e.type === "answer" && e.gate === gate?.id && e.target === qid && !e.stale) || null;
}

// ---------- sending ----------

const sentText = (data, ev) => (ev?.early ? "Saved for later. Claude asks you to confirm it when it gets to this step."
  : data?.listening ? "Sent. Claude is listening." : "Saved. Claude reads it when it next checks.");
export const waitingText = (data) => (data?.listening ? "Sent. Claude is on it." : "Saved, waiting for Claude");

/** An input for this step: early while the step is not started (gate null, "early": true). */
export function sendInput(ctx, data, step, id, value, type = "answer") {
  const ev = { type, step, gate: null, target: `${step}:${id}`, value };
  if (stateOf(data, step) === "pending") ev.early = true;
  return ctx.send(ev);
}

/** An answer to a question of the open gate; resolves to the stored event (check .stale). */
export function answerGate(ctx, gate, qid, value) {
  return ctx.send({ type: "answer", step: gate.step || null, gate: gate.id, target: qid, value });
}

/** The chip for a saved input: "Saved for later" (early), "Sent · waiting for Claude", "Claude has it". */
export function savedChip(data, ev) {
  if (!ev) return null;
  if (handled(data).has(ev.seq)) return chip("Claude has it", "ok");
  if (ev.early) return chip("Saved for later", "opt");
  return chip("Sent · waiting for Claude", "wait");
}

// ---------- inputs ----------

function field(label, forId, saved, ...kids) {
  return h("div", { class: "field" },
    h("div", { class: "row spread" }, forId ? h("label", { class: "lbl", for: forId }, label) : h("span", { class: "lbl" }, label),
      saved),
    ...kids);
}

/** A text box saved for Claude as an `answer` (target "<step>:<id>"). opts: {rows, placeholder, hint, mono, button} */
export function textInput(ctx, data, step, id, label, opts = {}) {
  const ev = lastInput(data, `${step}:${id}`);
  const fid = `in-${step}-${id}`;
  const value = typeof ev?.value === "string" ? ev.value : "";
  const attrs = { class: `f${opts.mono ? " mono" : ""}`, id: fid, "data-key": `in:${step}:${id}`, placeholder: opts.placeholder || "" };
  const box = opts.rows ? h("textarea", { ...attrs, rows: String(opts.rows) }, value) : h("input", { ...attrs, value, spellcheck: "false" });
  const note = h("div", { class: "msg", role: "status" });
  const btn = h("button", { class: "btn sm pri", type: "button" }, opts.button || "Save");
  btn.addEventListener("click", async () => {
    const v = box.value.trim();
    if (!v) { box.focus(); return; }
    btn.disabled = true;
    try {
      const sent = await sendInput(ctx, data, step, id, v);
      note.className = "msg ok";
      note.textContent = sentText(data, sent);
    } catch (e) {
      note.className = "msg err";
      note.textContent = e.message || "Not sent. Try again.";
    } finally {
      btn.disabled = false;
    }
  });
  return field(label, fid, savedChip(data, ev), opts.hint ? h("p", { class: "hint" }, opts.hint) : null, box,
    h("div", { class: "row", style: "margin-top:8px" }, btn), note);
}

/** Buttons for one choice, saved as an `answer` (target "<step>:<id>"). options: [[value, label]].
 *  opts: {current (a value already on the job card), answeredNote}. When the open gate asks the same question,
 *  the gate bar asks it and this shows a pointer instead. */
export function choiceInput(ctx, data, step, id, label, options, opts = {}) {
  if (gateAsks(data, step, id)) return field(label, null, null, h("p", { class: "hint" }, "Answer it in Claude's question above."));
  const ev = lastInput(data, `${step}:${id}`);
  const cur = ev ? ev.value : opts.current;
  const btns = options.map(([value, text]) => h("button", {
    class: `btn${cur === value ? " on" : ""}`, type: "button", "aria-pressed": String(cur === value),
    onclick: async () => {
      btns.forEach((b) => { b.disabled = true; });
      try {
        const sent = await sendInput(ctx, data, step, id, value);
        toast(sentText(data, sent));
      } catch (e) {
        toast(e.message || "Not sent. Try again.");
      } finally {
        btns.forEach((b) => { b.disabled = false; });
      }
    },
  }, text));
  const saved = ev ? savedChip(data, ev) : opts.current !== undefined && opts.current !== null && opts.current !== ""
    ? chip(opts.answeredNote || "already answered", "ok") : null;
  return field(label, null, saved, h("div", { class: "row", role: "group", "aria-label": label }, btns));
}

/** Files the server copied in for this step (its own `upload` events), newest last. */
export function uploads(data, step) {
  return (data?.events || []).filter((e) => e.type === "upload" && e.step === step && !e.early && typeof e.value === "string");
}

/** A drop zone for the step's files. While the step is not started, each file is also saved as an early `upload`
 *  event (target "<step>:upload") so Claude confirms it at the step's gate. */
export function uploadInput(ctx, data, step, kind, label) {
  const early = stateOf(data, step) === "pending";
  const ev = lastInput(data, `${step}:upload`);
  const files = uploads(data, step);
  return field(label, null, early ? savedChip(data, ev) : null,
    dropZone(kind, ctx, { label, onDone: async (res) => {
      if (!early) return;
      try { await sendInput(ctx, data, step, "upload", res.path, "upload"); } catch (e) { toast(e.message || "Not saved. Try again."); }
    } }),
    files.length ? h("ul", { class: "files" }, files.map((e) => h("li", { title: e.value },
      h("span", { class: "mono" }, baseName(e.value)), early ? null : savedChip(data, e)))) : null);
}

/** A button whose work changes files: an `action` event Claude acts on. opts: {primary, value() -> value | false} */
export function actionButton(ctx, data, step, target, label, opts = {}) {
  const pend = pendingFor(data, target);
  const note = h("span", { class: "hint", role: "status" }, pend.length ? waitingText(data) : "");
  const btn = h("button", { class: `btn${opts.primary ? " pri" : ""}`, type: "button" }, label);
  btn.addEventListener("click", async () => {
    const value = opts.value ? opts.value() : undefined;
    if (value === false) return;
    btn.disabled = true;
    try {
      await ctx.send({ type: "action", step, target, value });
      note.textContent = waitingText(data);
    } catch (e) {
      note.textContent = e.message || "Not sent. Try again.";
    } finally {
      btn.disabled = false;
    }
  });
  return h("span", { class: "row action" }, btn, pend.length ? pendingChip() : null, note);
}

/** An `edit` event for a field Claude applies to the real file; shows "pending" until handled. */
export async function sendEdit(ctx, step, target, value) {
  return ctx.send({ type: "edit", step, target, value });
}

// ---------- pieces ----------

/** "You" steps: what to do outside the app and where the file goes. */
export function youLine(text) {
  return h("div", { class: "banner you" }, chip("You", "you"), h("span", {}, text));
}

/** The red "Quit CapCut" banner while the open gate asks `capcut_closed`. Its button checks /api/capcut first;
 *  while CapCut still runs the "CapCut is still running" dialog rechecks every 2 s. */
export function capcutBanner(ctx, data, step) {
  const gate = openGate(data, step);
  const q = gate?.questions?.find((x) => x.id === CAPCUT_Q);
  if (!q) return null;
  const sent = gateAnswer(data, gate, q.id);
  const status = h("span", { class: "hint", role: "status" });
  const btn = h("button", { class: "btn pri", type: "button" }, "CapCut is closed");
  const answer = async (value) => {
    try {
      const ev = await answerGate(ctx, gate, q.id, value);
      btn.disabled = true;
      status.textContent = ev?.stale ? STALE_TEXT : "Sent · waiting for Claude";
    } catch (e) {
      status.textContent = e.message || "Not sent. Try again.";
      btn.disabled = false;
    }
  };
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    status.textContent = "Checking…";
    try {
      const r = await ctx.api("/api/capcut");
      if (r?.running) {
        status.textContent = "CapCut is still running.";
        btn.disabled = false;
        ctx.openDialog("capcut", { onClosed: () => answer(true), onCancel: () => answer("cancel") });
      } else {
        await answer(true);
      }
    } catch (e) {
      status.textContent = e.message || "Could not check CapCut. Try again.";
      btn.disabled = false;
    }
  });
  return h("div", { class: "banner err capcut", role: "alert" },
    h("div", {}, h("b", {}, "Quit CapCut completely before Claude writes"), h("div", { class: "hint" }, q.why || q.text)),
    sent ? h("span", { class: "row" }, chip(sent.value === "cancel" ? "Change cancelled" : "Sent · waiting for Claude", "wait"))
      : h("span", { class: "row" }, btn, status));
}

/** Every table output of the step (job.py output … kinds other than checklist/script), except `skip`. */
export function outputTables(ctx, data, step, opts = {}) {
  const skip = new Set(opts.skip || []);
  const out = [];
  for (const [kind, o] of Object.entries(outputsOf(data, step))) {
    if (skip.has(kind) || (opts.only && !opts.only(kind))) continue;
    if (o === null) {
      out.push(h("section", { class: "card" }, h("p", { class: "hint" }, `Claude's ${kind} output could not be read.`)));
    } else if (isTable(o)) {
      out.push(table(o, ctx, opts.actions ? { actions: (r) => opts.actions(r, kind, o) } : {}));
    }
  }
  return out;
}

/** The full prompt of a row (adapters.prompts puts plan_tools' rendered prompt in `prompt`), or null. Never the
 *  row's cells: Copy and the expanded prompt show only a real prompt, so nothing else gets pasted into a generator. */
export const promptText = (row) => (typeof row?.prompt === "string" && row.prompt.trim() ? row.prompt : null);

/** Step 6's prompt rows by id, across every prompts output (one per timeline). */
export function promptsById(data) {
  const by = new Map();
  for (const t of Object.values(data?.outputs?.prompts || {})) if (isTable(t)) t.rows.forEach((r) => by.set(String(r.id), r));
  return by;
}

export { copyButton };

// ---------- the page frame ----------

/** Draw a step page. parts: {you: text, early: () => Node[], body: () => Node[], hide: [gate question ids the page asks],
 *  labels: {question id: {yes, no}} (a confirm's button words in the gate bar; no: null drops No)} */
export function stepPage(root, step, data, ctx, parts = {}) {
  const job = data?.job;
  const st = stateOf(data, step);
  const name = String(ctx.folder || "").split("/").filter(Boolean).pop() || "";
  const gate = openGate(data, step);
  const hide = new Set([CAPCUT_Q, ...(parts.hide || [])]);
  const shown = gate ? { ...gate, questions: (gate.questions || []).filter((q) => !hide.has(q.id)) } : null;
  const answeredSome = gate && (gate.questions || []).some((q) => gateAnswer(data, gate, q.id));
  let content;
  if (st === "pending" && data?.early?.[step]) {
    content = [h("section", { class: "card early" }, h("div", { class: "row spread" }, h("h3", {}, "You can do this now"),
      chip("Open now", "opt")),
    h("p", { class: "hint" }, "Claude hasn't reached this step yet. What you save here waits for it; when Claude gets here it "
      + "asks you to confirm it instead of asking again."),
    h("div", { class: "stack" }, parts.early ? parts.early() : []))];
  } else if (st === "pending") {
    const prev = previousStep(step, job);
    content = [h("section", { class: "card coming" }, h("h2", {}, prev ? `Waits for: ${stepTitle(prev)}` : "Not started"),
      h("p", {}, `Claude opens ${stepTitle(step)} when it gets here. You can still write to Claude about it below.`))];
  } else {
    content = parts.body ? parts.body() : [];
  }
  root.append(...[  // the DOM's append stringifies null ("null" text), so the absent parts are filtered out
    nowStrip(data, "page"),
    h("div", { class: "crumbs" }, `${name} · Step ${STEPS.indexOf(step) + 1}`),
    h("div", { class: "head" }, h("div", {}, h("h1", {}, stepTitle(step)),
      h("p", { class: "why" }, h("span", { class: "sr" }, `${t("page.why_label")}: `), t(`why.${step}`), " ", h("span", { class: "takes" }, t(`time.${step}`))),
      job?.steps?.[step]?.note ? h("p", {}, job.steps[step].note) : null), stepChip(st)),
    parts.you ? youLine(parts.you) : null,
    shown ? gateBar(shown, ctx, parts.labels || {}) : null,
    capcutBanner(ctx, data, step),
    answeredSome && !data?.listening ? h("div", { class: "banner wait", role: "status" }, h("span", {}, NOT_LISTENING)) : null,
    h("div", { class: "stack" }, content),
    askBox(step, data, ctx)].filter(Boolean));
}
