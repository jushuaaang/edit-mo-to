// Captions (step 10): the two choices side by side: "I'll run CapCut auto-caption" (then "Auto-caption is done") or
// "Claude adds them" (timelines, then Add captions, an action), and the TEMP_EN reminder.
// Gates: who adds captions; timelines; quit CapCut (the red banner). While the open gate asks `timelines`, "Add captions"
// answers it (the gate bar hides it); otherwise the button sends the `captions:add` action, which Claude confirms at the gate.
import { h, chip, STALE_TEXT } from "../ui.js";
import { stepPage, choiceInput, lastInput, actionButton, timelines, card, gateAsks, openGate, gateAnswer, answerGate,
  waitingText } from "../steppage.js";

const WHO = [["me", "I'll run CapCut auto-caption"], ["claude", "Claude adds them"]];

function tempEnLine(data) {
  const t = String(card(data).temp_en || "");
  if (t !== "on" && !t.startsWith("partial:")) return null;
  return h("div", { class: "banner err", role: "note" }, h("b", {}, "TEMP_EN is still on."),
    h("span", {}, "The TEMP_EN_delete_me track is only for review. Delete it before export; captions use the script's own words."));
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
    : timelines(data).map((t) => ({ value: t, label: t }));
  const defaults = gq && Array.isArray(gq.default) ? gq.default.map(String) : null;
  const tls = opts.map((o) => o.label);
  const boxes = opts.map((o) => h("input", { type: "checkbox", value: o.value, checked: defaults ? defaults.includes(o.value) : true,
    "data-key": `cap:${o.value}` }));
  return h("div", { class: "grid2" },
    h("section", { class: `card choice${who === "me" ? " picked" : ""}` }, h("h3", {}, "I'll run CapCut auto-caption"),
      h("p", { class: "hint" }, "In CapCut: Text → Auto captions on each timeline, then pick a caption preset for an animated look."),
      who === "me" ? actionButton(ctx, data, "captions", "captions:auto-done", "Auto-caption is done", { primary: true }) : null),
    h("section", { class: `card choice${who === "claude" ? " picked" : ""}` }, h("h3", {}, "Claude adds them"),
      h("p", { class: "hint" }, "Simple text captions with the script's exact words and a pop-in; no word-by-word animation."),
      who === "claude" ? h("div", { class: "stack" },
        tls.length ? h("div", { class: "row", role: "group", "aria-label": "Timelines" },
          tls.map((t, i) => h("label", { class: "check" }, boxes[i], t))) : null,
        gate ? addAnswer(ctx, data, gate, () => boxes.filter((b) => b.checked).map((b) => b.value))
          : actionButton(ctx, data, "captions", "captions:add", "Add captions", { primary: true,
            value: () => (tls.length ? boxes.filter((b) => b.checked).map((b) => b.value) : null) })) : null));
}

/** The open gate asks `timelines`: "Add captions" answers it; the red banner still asks `capcut_closed`. */
function addAnswer(ctx, data, gate, picked) {
  const sent = gateAnswer(data, gate, "timelines");
  if (sent) return h("span", { class: "row" }, chip("Timelines sent · waiting for Claude", "wait"));
  const note = h("span", { class: "hint", role: "status" });
  const btn = h("button", { class: "btn pri", type: "button" }, "Add captions");
  btn.addEventListener("click", async () => {
    const value = picked();
    if (!value.length) { note.textContent = "Pick at least one timeline."; return; }
    btn.disabled = true;
    try {
      const ev = await answerGate(ctx, gate, "timelines", value);
      note.textContent = ev?.stale ? STALE_TEXT : waitingText(data);
    } catch (e) {
      note.textContent = e.message || "Not sent. Try again.";
      btn.disabled = false;
    }
  });
  return h("span", { class: "row action" }, btn, note);
}

export function render(root, data, ctx) {
  const pick = () => choiceInput(ctx, data, "captions", "who", "Who adds the captions?", WHO);
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
