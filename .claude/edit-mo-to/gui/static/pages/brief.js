// Brief (steps 1-2): brief link, paste box, one "Additional instructions" box, reference files (refs/),
// the picked style and script language, the brief checklist, and Claude's questions about the brief.
// Gate on the page: confirm the checklist and style.
import { h, chip, toast, staleText, copyButton } from "../ui.js";
import { t } from "../words.js";
import { stepPage, uploadInput, outputsOf, openGate, card, sendInput, answerGate, field, lastInput, savedChip, uploads }
  from "../steppage.js";

const STATUS = { confirmed: "ok", open: "you", question: "you", missing: "err", conflict: "err" };
const LAUNCH_FALLBACK = new Set(["no-claude", "failed", "unsupported"]);  // these replies show the Copy fallback
const LAUNCH_WHY = { "no-claude": "practice.no_claude", failed: "practice.failed", unsupported: "practice.unsupported",
  busy: "practice.busy" };
const BOXES = [["link", "brief.link", { placeholder: "https://…", mono: true }],
  ["paste", "brief.paste", { rows: 5, placeholder: "brief.paste_ph" }],
  ["instructions", "brief.instructions", { rows: 3, placeholder: "brief.instructions_ph" }]];

/** The brief: link, pasted text and instructions (no Save per box), the reference files (copied as they drop), and one
 *  Submit to Claude: it sends each box whose text changed as a `brief:<id>` answer, then the `brief:submit` action that
 *  tells Claude the brief is complete (it wakes a listening Claude; otherwise Claude reads it when it next checks). */
function inputs(ctx, data) {
  const boxes = BOXES.map(([id, label, o]) => {
    const ev = lastInput(data, `brief:${id}`);
    const value = typeof ev?.value === "string" ? ev.value : "";
    const attrs = { class: `f${o.mono ? " mono" : ""}`, id: `in-brief-${id}`, "data-key": `in:brief:${id}`,
      placeholder: o.placeholder.startsWith("brief.") ? t(o.placeholder) : o.placeholder };
    const box = o.rows ? h("textarea", { ...attrs, rows: String(o.rows) }, value) : h("input", { ...attrs, value, spellcheck: "false" });
    return { id, box, sent: value, node: field(t(label), attrs.id, savedChip(data, ev), box) };
  });
  const note = h("div", { class: "msg", role: "status" });
  const fallback = h("div", { class: "row fallback", hidden: true });
  const key = String(data?.job?.folder || ctx.folder || "");
  live.set(key, { note, fallback });  // the message line on screen now (a refresh replaces it)
  const show = (st) => { submitted.set(key, st); const on = live.get(key); paint(on.note, on.fallback, st); };
  paint(note, fallback, submitted.get(key));  // the page refreshes after a send: the outcome stays on screen
  const btn = h("button", { class: "btn pri", type: "button" }, t("brief.submit"));
  btn.addEventListener("click", async () => {
    // every box is optional, but Claude needs something to work on: text, a link, instructions or a file
    if (!boxes.some((b) => b.box.value.trim()) && !uploads(data, "brief").length) {
      show({ cls: "msg err", text: t("brief.need_something") });
      boxes[1].box.focus();
      return;
    }
    btn.disabled = true;
    try {
      for (const b of boxes) {
        const v = b.box.value.trim();
        if (v && v !== b.sent) { await sendInput(ctx, data, "brief", b.id, v); b.sent = v; }
      }
      await ctx.send({ type: "action", step: "brief", target: "brief:submit" });
      editing.delete(key);  // sent: the boxes give way to the summary on the next refresh
      show({ cls: "msg ok", text: t("brief.submitted") });
      if (!data?.listening) await openClaude(ctx, data, show);
    } catch (e) {
      show({ cls: "msg err", text: e.message || t("common.not_sent") });
    } finally {
      btn.disabled = false;
    }
  });
  return [...boxes.map((b) => b.node), uploadInput(ctx, data, "brief", "refs", t("brief.refs")),
    h("div", { class: "row", style: "margin-top:8px" }, btn), note, fallback];
}

/** No Claude is listening: open the editor's own Claude in a window on this video (POST /api/practice, a fixed command:
 *  /practice-muna-app for a practice video, /edit-mo-to-app for a real one; it finds the video as the app's current job).
 *  When it can't (no `claude` command, the launch failed, or this system can't open a window) say why in plain words
 *  and show "In Claude, type: <command> [Copy]". */
async function openClaude(ctx, data, show) {
  const practice = /[\\/]_practice[\\/]/.test(String(data?.job?.folder || ctx.folder || ""));
  const command = practice ? "practice-muna" : "edit-mo-to";
  show({ cls: "hint", text: t("practice.starting") });
  let reply;
  try {
    reply = await ctx.api("/api/practice", { body: { command } });
  } catch {
    reply = { ok: false, reason: "failed" };
  }
  if (!reply?.ok && !LAUNCH_WHY[reply?.reason]) reply = { ok: false, reason: "failed" };
  show({ cls: reply.ok || reply.reason === "busy" ? "msg ok" : "msg err",
    text: reply.ok ? t(reply.attached ? "practice.attached" : "practice.opened")
      : [t(LAUNCH_WHY[reply.reason]), reply.hint === "automation" ? t("practice.mac_automation") : ""].filter(Boolean).join(" "),
    typed: reply.ok || !LAUNCH_FALLBACK.has(reply.reason) ? null : `/${command}-app` });
}

/** The last Submit outcome per video ({cls, text, typed}): kept here because sending refreshes the page. */
const submitted = new Map();
/** The message line and Copy fallback on screen per video: a launch reply that lands after a refresh goes there. */
const live = new Map();

function paint(note, fallback, st) {
  note.className = st?.cls || "msg";
  note.textContent = st?.text || "";
  fallback.hidden = !st?.typed;
  fallback.replaceChildren(...(st?.typed ? [h("span", {}, t("practice.type")), h("code", { class: "mono cmd" }, st.typed),
    copyButton(st.typed, t("practice.copy"))] : []));
}

function styleLine(data, checklist) {
  const c = card(data);
  const style = c.style || checklist?.style;
  const lang = c.language || checklist?.language;
  return h("section", { class: "card" }, h("h3", {}, t("brief.style_h")),
    h("div", { class: "row" }, h("span", { class: "lbl", style: "margin:0" }, t("brief.style")), style ? h("b", {}, style) : h("span", { class: "hint" }, t("brief.style_none")),
      h("span", { class: "lbl", style: "margin:0 0 0 16px" }, t("brief.script_lang")), lang ? h("b", {}, lang) : h("span", { class: "hint" }, t("brief.not_set"))));
}

function checklistCard(checklist) {
  const rules = checklist?.rules || [];
  return h("section", { class: "card" }, h("h3", {}, t("brief.checklist_h")),
    rules.length ? h("div", { class: "tablewrap" }, h("table", {},
      h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "#"), h("th", { scope: "col" }, t("brief.th_rule")), h("th", { scope: "col" }, t("brief.th_source")),
        h("th", { scope: "col" }, t("table.status")))),
      h("tbody", {}, rules.map((r) => h("tr", {}, h("td", { class: "mono" }, String(r.n ?? "")), h("td", {}, String(r.rule ?? "")),
        h("td", { class: "hint" }, String(r.source ?? "")), h("td", {}, chip(String(r.status ?? ""), STATUS[String(r.status).toLowerCase()] || "mute")))))))
      : h("p", { class: "hint" }, t("brief.checklist_empty")));
}

/** Claude's questions (up to 6), each with its own box; all answers go as one `answer` event to the open gate. */
function questionsCard(ctx, data, checklist) {
  const qs = (checklist?.questions || []).slice(0, 6);
  if (!qs.length) return null;
  const gate = openGate(data, "brief");
  const sent = [...(data?.events || [])].reverse().find((e) => e.type === "answer" && e.target === (gate ? "questions" : "brief:questions")
    && (gate ? e.gate === gate.id : true) && !e.stale);
  const prev = sent && typeof sent.value === "object" && sent.value ? sent.value : {};
  const boxes = qs.map((q) => h("textarea", { class: "f", rows: "2", id: `bq-${q.id}`, "data-key": `brief-q:${q.id}` },
    typeof prev[q.id] === "string" ? prev[q.id] : ""));
  const note = h("div", { class: "msg", role: "status" });
  const btn = h("button", { class: "btn pri", type: "button" }, t("brief.send_answers"));
  btn.addEventListener("click", async () => {
    const value = {};
    qs.forEach((q, i) => { if (boxes[i].value.trim()) value[q.id] = boxes[i].value.trim(); });
    if (!Object.keys(value).length) { boxes[0].focus(); return; }
    btn.disabled = true;
    try {
      const ev = gate ? await answerGate(ctx, gate, "questions", value) : await sendInput(ctx, data, "brief", "questions", value);
      note.className = ev?.stale ? "msg err" : "msg ok";
      note.textContent = ev?.stale ? staleText() : t(data?.listening ? "common.sent_listening" : "common.saved_later");
    } catch (e) {
      toast(e.message || t("common.not_sent"));
    } finally {
      btn.disabled = false;
    }
  });
  return h("section", { class: "card" }, h("div", { class: "row spread" }, h("h3", {}, t("brief.questions_h")),
    sent ? chip(t("common.sent_waiting"), "wait") : null),
  h("div", { class: "stack" }, qs.map((q, i) => h("div", { class: "field" },
    h("label", { class: "qt", for: `bq-${q.id}` }, String(q.text ?? "")), q.why ? h("div", { class: "hint" }, String(q.why)) : null, boxes[i]))),
  h("div", { class: "row", style: "margin-top:10px" }, btn), note);
}

/** Step 1 has two views. Before Submit: "Your brief" (the boxes). After Submit: Claude's side only (its question, the
 *  checklist, its questions about the brief), with a "See or edit your brief" button that switches back to the boxes;
 *  "Back to Claude's checklist" (or the next Submit) returns. */
const editing = new Set();  // videos showing the brief boxes again after Submit
const wasSubmitted = (data) => (data?.events || []).some((e) => e.type === "action" && e.target === "brief:submit" && !e.stale);
const keyOf = (ctx, data) => String(data?.job?.folder || ctx.folder || "");

/** The Submit outcome (Sent / Claude is opening / why not + Copy), kept across refreshes. */
function outcome(ctx, data) {
  const key = keyOf(ctx, data);
  const note = h("div", { class: "msg", role: "status" });
  const fallback = h("div", { class: "row fallback", hidden: true });
  live.set(key, { note, fallback });
  paint(note, fallback, submitted.get(key));
  return [note, fallback];
}

function switchView(root, data, ctx, toBoxes) {
  if (toBoxes) editing.add(keyOf(ctx, data)); else editing.delete(keyOf(ctx, data));
  root.replaceChildren();
  render(root, data, ctx);
}

export function render(root, data, ctx) {
  const checklist = outputsOf(data, "brief").checklist;
  const sent = wasSubmitted(data) && !editing.has(keyOf(ctx, data));
  if (!sent) {
    const back = wasSubmitted(data)
      ? h("button", { class: "btn sm", type: "button", onclick: () => switchView(root, data, ctx, false) }, t("brief.back"))
      : null;
    const boxes = [back ? h("div", { class: "row" }, back) : null, ...inputs(ctx, data)].filter(Boolean);
    stepPage(root, "brief", data, ctx, {
      early: () => boxes,
      body: () => [h("section", { class: "card" }, h("h3", {}, t("brief.the_brief")), h("div", { class: "stack" }, boxes))],
    });
    return;
  }
  const see = h("div", { class: "row" },
    h("button", { class: "btn sm", type: "button", onclick: () => switchView(root, data, ctx, true) }, t("brief.see")));
  const asking = Boolean(openGate(data, "brief"));
  const qs = (checklist?.questions || []).slice(0, 6);
  stepPage(root, "brief", data, ctx, {
    early: () => [h("p", {}, t("brief.waiting_claude")), ...outcome(ctx, data), see],
    // while Claude asks, its questions about the brief are in the question bar and go with Proceed (one answer, target
    // "questions"); the card with its own Send shows only when no question is open
    gateExtra: () => (qs.length ? { target: "questions", questions: qs } : null),
    body: () => [...outcome(ctx, data), checklistCard(checklist), asking ? null : questionsCard(ctx, data, checklist),
      styleLine(data, checklist), see].filter(Boolean),
  });
}
