// Timing & cleanup (step 5): the line timings table with every unmatched line highlighted (Keep / Re-record),
// and for talking-head A-roll the cuts table with a checkbox per cut and "Apply selected cuts" (an action).
// Gates: unmatched lines; which cuts. While the open gate asks `cuts`, "Apply selected cuts" answers it (the gate bar
// hides it); otherwise the button sends the `timing:apply-cuts` action, which Claude confirms at the gate.
import { h, chip, pendingChip, toast, table, staleText } from "../ui.js";
import { t } from "../words.js";
import { stepPage, outputsOf, outputTables, isTable, actionButton, pendingFor, sendEdit, waitingText, gateAsks, openGate,
  gateAnswer, answerGate } from "../steppage.js";

function timingsCard(ctx, data, tb) {
  const el = table(tb, ctx, { actions: (r) => {
    if (r.status !== "err") return null;
    const target = `timing:${r.id}`;
    const pend = pendingFor(data, target).pop();
    const pick = async (value) => {
      try { await sendEdit(ctx, "timing", target, value); toast(waitingText(data)); } catch (e) { toast(e.message || t("common.not_sent")); }
    };
    return h("span", { class: "row" },
      h("button", { class: `btn sm${pend?.value === "keep" ? " on" : ""}`, type: "button", onclick: () => pick("keep") }, t("timing.keep")),
      h("button", { class: `btn sm${pend?.value === "rerecord" ? " on" : ""}`, type: "button", onclick: () => pick("rerecord") }, t("timing.rerecord")),
      pend ? pendingChip() : null);
  } });
  tb.rows.forEach((r) => { if (r.status === "err") el.querySelector(`tr[data-id="${CSS.escape(String(r.id))}"]`)?.classList.add("flag"); });
  return el;
}

function cutsCard(ctx, data, tb) {
  const boxes = new Map();
  const el = table(tb, ctx, { words: { ok: t("timing.w_cut"), you: t("timing.w_review") }, actions: (r) => {
    const box = h("input", { type: "checkbox", checked: r.status === "ok", "data-key": `cut:${r.id}`, "aria-label": t("timing.cut_label", { id: r.id }) });
    boxes.set(String(r.id), box);
    return h("label", { class: "check" }, box, t("timing.cut"));
  } });
  const picked = () => [...boxes].filter(([, b]) => b.checked).map(([id]) => id);
  el.append(h("div", { class: "row", style: "margin-top:10px" }, gateAsks(data, "timing", "cuts")
    ? cutsAnswer(ctx, data, picked)
    : actionButton(ctx, data, "timing", "timing:apply-cuts", t("timing.apply"), { primary: true,
      value: () => ({ approve: picked(), reject: [...boxes].filter(([, b]) => !b.checked).map(([id]) => id) }) })));
  return el;
}

/** The open gate asks `cuts`: the button answers it with the checked cut ids (never a second, separate action). */
function cutsAnswer(ctx, data, picked) {
  const gate = openGate(data, "timing");
  const sent = gateAnswer(data, gate, "cuts");
  if (sent) return h("span", { class: "row" }, chip(t("timing.cuts_sent"), "wait"));
  const note = h("span", { class: "hint", role: "status" });
  const btn = h("button", { class: "btn pri", type: "button" }, t("timing.apply"));
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    try {
      const ev = await answerGate(ctx, gate, "cuts", picked());
      note.textContent = ev?.stale ? staleText() : waitingText(data);
    } catch (e) {
      note.textContent = e.message || t("common.not_sent");
      btn.disabled = false;
    }
  });
  return h("span", { class: "row action" }, btn, note);
}

export function render(root, data, ctx) {
  const out = outputsOf(data, "timing");
  stepPage(root, "timing", data, ctx, {
    hide: isTable(out.cuts) && gateAsks(data, "timing", "cuts") ? ["cuts"] : [],  // the cuts table's button answers it
    body: () => [
      isTable(out.timings) ? timingsCard(ctx, data, out.timings)
        : h("section", { class: "card" }, h("h3", {}, t("timing.h")), h("p", { class: "hint" }, t("timing.empty"))),
      isTable(out.cuts) ? cutsCard(ctx, data, out.cuts) : null,
      ...outputTables(ctx, data, "timing", { skip: ["timings", "cuts"] }),
    ],
  });
}
