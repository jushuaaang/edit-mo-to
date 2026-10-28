// Brief (steps 1-2): brief link, paste box, one "Additional instructions" box, reference files (refs/),
// the picked style and script language, the brief checklist, and Claude's questions about the brief.
// Gate on the page: confirm the checklist and style.
import { h, chip, toast, staleText } from "../ui.js";
import { t } from "../words.js";
import { stepPage, textInput, uploadInput, outputsOf, openGate, card, sendInput, answerGate } from "../steppage.js";

const STATUS = { confirmed: "ok", open: "you", question: "you", missing: "err", conflict: "err" };

function inputs(ctx, data) {
  return [
    textInput(ctx, data, "brief", "link", t("brief.link"), { placeholder: "https://…", mono: true }),
    textInput(ctx, data, "brief", "paste", t("brief.paste"), { rows: 5, placeholder: t("brief.paste_ph") }),
    textInput(ctx, data, "brief", "instructions", t("brief.instructions"), { rows: 3, placeholder: t("brief.instructions_ph") }),
    uploadInput(ctx, data, "brief", "refs", t("brief.refs")),
  ];
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

export function render(root, data, ctx) {
  const checklist = outputsOf(data, "brief").checklist;
  stepPage(root, "brief", data, ctx, {
    early: () => inputs(ctx, data),
    body: () => [
      h("section", { class: "card" }, h("h3", {}, t("brief.the_brief")), h("div", { class: "stack" }, inputs(ctx, data))),
      styleLine(data, checklist), checklistCard(checklist), questionsCard(ctx, data, checklist),
    ],
  });
}
