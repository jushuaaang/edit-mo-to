// Captions (step 10): the two choices side by side: "I'll run CapCut auto-caption" (then "Auto-caption is done") or
// "Claude adds them" (timelines, then Add captions, an action), and the TEMP_EN reminder.
// Gates: who adds captions; timelines; quit CapCut.
import { h } from "../ui.js";
import { stepPage, choiceInput, lastInput, actionButton, timelines, card } from "../steppage.js";

const WHO = [["me", "I'll run CapCut auto-caption"], ["claude", "Claude adds them"]];

function tempEnLine(data) {
  const t = String(card(data).temp_en || "");
  if (t !== "on" && !t.startsWith("partial:")) return null;
  return h("div", { class: "banner err", role: "note" }, h("b", {}, "TEMP_EN is still on."),
    h("span", {}, "The TEMP_EN_delete_me track is only for review. Delete it before export; captions use the script's own words."));
}

function sides(ctx, data) {
  const who = lastInput(data, "captions:who")?.value  // the page's choice, or the gate's answer to "who"
    ?? [...(data?.events || [])].reverse().find((e) => e.type === "answer" && e.step === "captions" && e.target === "who" && !e.stale)?.value;
  const tls = timelines(data);
  const boxes = tls.map((t) => h("input", { type: "checkbox", value: t, checked: true, "data-key": `cap:${t}` }));
  return h("div", { class: "grid2" },
    h("section", { class: `card choice${who === "me" ? " picked" : ""}` }, h("h3", {}, "I'll run CapCut auto-caption"),
      h("p", { class: "hint" }, "In CapCut: Text → Auto captions on each timeline, then pick a caption preset for an animated look."),
      who === "me" ? actionButton(ctx, data, "captions", "captions:auto-done", "Auto-caption is done", { primary: true }) : null),
    h("section", { class: `card choice${who === "claude" ? " picked" : ""}` }, h("h3", {}, "Claude adds them"),
      h("p", { class: "hint" }, "Simple text captions with the script's exact words and a pop-in; no word-by-word animation."),
      who === "claude" ? h("div", { class: "stack" },
        tls.length ? h("div", { class: "row", role: "group", "aria-label": "Timelines" },
          tls.map((t, i) => h("label", { class: "check" }, boxes[i], t))) : null,
        actionButton(ctx, data, "captions", "captions:add", "Add captions", { primary: true,
          value: () => (tls.length ? boxes.filter((b) => b.checked).map((b) => b.value) : null) })) : null));
}

export function render(root, data, ctx) {
  const pick = () => choiceInput(ctx, data, "captions", "who", "Who adds the captions?", WHO);
  stepPage(root, "captions", data, ctx, {
    early: () => [pick()],
    body: () => [
      tempEnLine(data),
      h("section", { class: "card" }, pick()),
      sides(ctx, data),
    ],
  });
}
