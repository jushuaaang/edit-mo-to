// Captions (step 10): the two choices side by side: "I'll run CapCut auto-caption" (then "Auto-caption is done") or
// "Claude adds them" (timelines, then Add captions, an action), and the TEMP_EN reminder.
// Gates: who adds captions; timelines; quit CapCut (the red banner). While the open gate asks `timelines`, "Add captions"
// answers it (the gate bar hides it); otherwise the button sends the `captions:add` action, which Claude confirms at the gate.
import { h, chip, helpTip, staleText } from "../ui.js";
import { t } from "../words.js";
import { stepPage, choiceInput, lastInput, actionButton, timelines, card, gateAsks, openGate, gateAnswer, answerGate,
  waitingText } from "../steppage.js";

const WHO = [["me", "captions.me"], ["claude", "captions.claude"]];  // value, word

function tempEnLine(data) {
  const te = String(card(data).temp_en || "");
  if (te !== "on" && !te.startsWith("partial:")) return null;
  return h("div", { class: "banner err", role: "note" }, h("b", {}, t("captions.temp_on"), helpTip("temp_en")),
    h("span", {}, t("captions.temp_p")));
}

/** Who adds the captions: the page's choice, or the gate's answer to "who". */
const whoOf = (data) => lastInput(data, "captions:who")?.value
  ?? [...(data?.events || [])].reverse().find((e) => e.type === "answer" && e.step === "captions" && e.target === "who" && !e.stale)?.value;

function sides(ctx, data) {
  const who = whoOf(data);
  const gate = gateAsks(data, "captions", "timelines") ? openGate(data, "captions") : null;
  const gq = gate?.questions?.find((q) => q.id === "timelines");
  // the gate's own options (and defaults) when it asks; else the job card's timelines
  const opts = gq && Array.isArray(gq.options) && gq.options.length
    ? gq.options.map((o) => (typeof o === "object" && o !== null ? { value: String(o.value ?? o.label), label: String(o.label ?? o.value) }
      : { value: String(o), label: String(o) }))
    : timelines(data).map((n) => ({ value: n, label: n }));
  const defaults = gq && Array.isArray(gq.default) ? gq.default.map(String) : null;
  const tls = opts.map((o) => o.label);
  const boxes = opts.map((o) => h("input", { type: "checkbox", value: o.value, checked: defaults ? defaults.includes(o.value) : true,
    "data-key": `cap:${o.value}` }));
  return h("div", { class: "grid2" },
    h("section", { class: `card choice${who === "me" ? " picked" : ""}` }, h("h3", {}, t("captions.me")),
      h("p", { class: "hint" }, t("captions.me_p")),
      who === "me" ? actionButton(ctx, data, "captions", "captions:auto-done", t("captions.auto_done"), { primary: true }) : null),
    h("section", { class: `card choice${who === "claude" ? " picked" : ""}` }, h("h3", {}, t("captions.claude")),
      h("p", { class: "hint" }, t("captions.claude_p")),
      who === "claude" ? h("div", { class: "stack" },
        tls.length ? h("div", { class: "row", role: "group", "aria-label": t("captions.timelines") },
          tls.map((n, i) => h("label", { class: "check" }, boxes[i], n))) : null,
        gate ? addAnswer(ctx, data, gate, () => boxes.filter((b) => b.checked).map((b) => b.value))
          : actionButton(ctx, data, "captions", "captions:add", t("captions.add"), { primary: true,
            value: () => (tls.length ? boxes.filter((b) => b.checked).map((b) => b.value) : null) })) : null));
}

/** The open gate asks `timelines`: "Add captions" answers it; the red banner still asks `capcut_closed`. */
function addAnswer(ctx, data, gate, picked) {
  const sent = gateAnswer(data, gate, "timelines");
  if (sent) return h("span", { class: "row" }, chip(t("captions.tl_sent"), "wait"));
  const note = h("span", { class: "hint", role: "status" });
  const btn = h("button", { class: "btn pri", type: "button" }, t("captions.add"));
  btn.addEventListener("click", async () => {
    const value = picked();
    if (!value.length) { note.textContent = t("captions.pick_one"); return; }
    btn.disabled = true;
    try {
      const ev = await answerGate(ctx, gate, "timelines", value);
      note.textContent = ev?.stale ? staleText() : waitingText(data);
    } catch (e) {
      note.textContent = e.message || t("common.not_sent");
      btn.disabled = false;
    }
  });
  return h("span", { class: "row action" }, btn, note);
}

export function render(root, data, ctx) {
  const pick = () => choiceInput(ctx, data, "captions", "who", t("captions.who"), WHO.map(([v, k]) => [v, t(k)]));
  const who = whoOf(data);
  stepPage(root, "captions", data, ctx, {
    // "Add captions" answers `timelines` when it is drawn (the editor chose "Claude adds them"); else the gate bar asks it
    hide: who === "claude" && gateAsks(data, "captions", "timelines") ? ["timelines"] : [],
    early: () => [pick()],
    body: () => [
      tempEnLine(data),
      h("section", { class: "card" }, pick()),
      sides(ctx, data),
    ],
  });
}
