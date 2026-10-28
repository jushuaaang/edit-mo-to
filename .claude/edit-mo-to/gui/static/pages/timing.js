// Timing & cleanup (step 5): the line timings table with every unmatched line highlighted (Keep / Re-record),
// and for talking-head A-roll the cuts table with a checkbox per cut and "Apply selected cuts" (an action).
// Gates: unmatched lines; which cuts.
import { h, pendingChip, toast, table } from "../ui.js";
import { stepPage, outputsOf, outputTables, isTable, actionButton, pendingFor, sendEdit, waitingText } from "../steppage.js";

function timingsCard(ctx, data, t) {
  const el = table(t, ctx, { actions: (r) => {
    if (r.status !== "err") return null;
    const target = `timing:${r.id}`;
    const pend = pendingFor(data, target).pop();
    const pick = async (value) => {
      try { await sendEdit(ctx, "timing", target, value); toast(waitingText(data)); } catch (e) { toast(e.message || "Not sent. Try again."); }
    };
    return h("span", { class: "row" },
      h("button", { class: `btn sm${pend?.value === "keep" ? " on" : ""}`, type: "button", onclick: () => pick("keep") }, "Keep"),
      h("button", { class: `btn sm${pend?.value === "rerecord" ? " on" : ""}`, type: "button", onclick: () => pick("rerecord") }, "Re-record"),
      pend ? pendingChip() : null);
  } });
  t.rows.forEach((r) => { if (r.status === "err") el.querySelector(`tr[data-id="${CSS.escape(String(r.id))}"]`)?.classList.add("flag"); });
  return el;
}

function cutsCard(ctx, data, t) {
  const boxes = new Map();
  const el = table(t, ctx, { words: { ok: "Cut", you: "Review" }, actions: (r) => {
    const box = h("input", { type: "checkbox", checked: r.status === "ok", "data-key": `cut:${r.id}`, "aria-label": `Cut ${r.id}` });
    boxes.set(String(r.id), box);
    return h("label", { class: "check" }, box, "cut");
  } });
  el.append(h("div", { class: "row", style: "margin-top:10px" },
    actionButton(ctx, data, "timing", "timing:apply-cuts", "Apply selected cuts", { primary: true,
      value: () => ({ approve: [...boxes].filter(([, b]) => b.checked).map(([id]) => id),
        reject: [...boxes].filter(([, b]) => !b.checked).map(([id]) => id) }) })));
  return el;
}

export function render(root, data, ctx) {
  const out = outputsOf(data, "timing");
  stepPage(root, "timing", data, ctx, {
    body: () => [
      isTable(out.timings) ? timingsCard(ctx, data, out.timings)
        : h("section", { class: "card" }, h("h3", {}, "Line timings"), h("p", { class: "hint" }, "Claude times the voiceover after it's in.")),
      isTable(out.cuts) ? cutsCard(ctx, data, out.cuts) : null,
      ...outputTables(ctx, data, "timing", { skip: ["timings", "cuts"] }),
    ],
  });
}
