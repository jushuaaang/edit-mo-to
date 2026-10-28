// Timing & cleanup (step 5): the line timings table with every unmatched line highlighted (Keep / Re-record),
// and for talking-head A-roll the cuts table with a checkbox per cut and "Apply selected cuts" (an action).
// Gates: unmatched lines; which cuts. While the open gate asks `cuts`, "Apply selected cuts" answers it (the gate bar
// hides it); otherwise the button sends the `timing:apply-cuts` action, which Claude confirms at the gate.
import { h, chip, pendingChip, toast, table, STALE_TEXT } from "../ui.js";
import { stepPage, outputsOf, outputTables, isTable, actionButton, pendingFor, sendEdit, waitingText, gateAsks, openGate,
  gateAnswer, answerGate } from "../steppage.js";

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
  const picked = () => [...boxes].filter(([, b]) => b.checked).map(([id]) => id);
  el.append(h("div", { class: "row", style: "margin-top:10px" }, gateAsks(data, "timing", "cuts")
    ? cutsAnswer(ctx, data, picked)
    : actionButton(ctx, data, "timing", "timing:apply-cuts", "Apply selected cuts", { primary: true,
      value: () => ({ approve: picked(), reject: [...boxes].filter(([, b]) => !b.checked).map(([id]) => id) }) })));
  return el;
}

/** The open gate asks `cuts`: the button answers it with the checked cut ids (never a second, separate action). */
function cutsAnswer(ctx, data, picked) {
  const gate = openGate(data, "timing");
  const sent = gateAnswer(data, gate, "cuts");
  if (sent) return h("span", { class: "row" }, chip("Cuts sent · waiting for Claude", "wait"));
  const note = h("span", { class: "hint", role: "status" });
  const btn = h("button", { class: "btn pri", type: "button" }, "Apply selected cuts");
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    try {
      const ev = await answerGate(ctx, gate, "cuts", picked());
      note.textContent = ev?.stale ? STALE_TEXT : waitingText(data);
    } catch (e) {
      note.textContent = e.message || "Not sent. Try again.";
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
        : h("section", { class: "card" }, h("h3", {}, "Line timings"), h("p", { class: "hint" }, "Claude times the voiceover after it's in.")),
      isTable(out.cuts) ? cutsCard(ctx, data, out.cuts) : null,
      ...outputTables(ctx, data, "timing", { skip: ["timings", "cuts"] }),
    ],
  });
}
