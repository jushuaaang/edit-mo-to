// Review (step 9, the editor's): the CapCut banner once per round (from the gate), the change list (change, timeline,
// in place / new timeline, status), "Send changes", "I'm happy, go to captions", and the editor's own edits found by
// edit_diff. Gates: which timeline; in place or new; quit CapCut.
// Changes not yet sent are drafts in gui.json (`review_drafts`); "Send changes" is one `edit` event (target
// "review:changes"); a change in place first shows the `inplace` dialog (where the backup goes).
import { h, pendingChip, toast } from "../ui.js";
import { stepPage, outputsOf, outputTables, isTable, actionButton, pendingFor, sendEdit, timelines, card, waitingText } from "../steppage.js";

const MODES = [["inplace", "In place (backup first)"], ["new", "New timeline"]];

function draftsCard(ctx, data) {
  const drafts = Array.isArray(data?.gui?.review_drafts) ? data.gui.review_drafts : [];
  const tls = timelines(data);
  const text = h("textarea", { class: "f", rows: "2", id: "rv-text", "data-key": "review:text",
    placeholder: "What should change? e.g. “Hook 2: swap the 0:04 clip for the jar close-up”" });
  const tl = h("select", { class: "f", id: "rv-tl", "data-key": "review:tl" },
    h("option", { value: "" }, "Which timeline?"), tls.map((t) => h("option", { value: t }, t)), h("option", { value: "all" }, "All timelines"));
  const mode = h("select", { class: "f", id: "rv-mode", "data-key": "review:mode" }, MODES.map(([v, l]) => h("option", { value: v }, l)));
  const save = (list) => ctx.saveGui({ review_drafts: list.length ? list : null }).catch((e) => toast(e.message || "Not saved."));
  const add = h("button", { class: "btn", type: "button", onclick: () => {
    if (!text.value.trim()) { text.focus(); return; }
    const draft = { text: text.value.trim(), timeline: tl.value || null, mode: mode.value };
    text.value = "";
    save([...drafts, draft]);
  } }, "Add to the list");
  const note = h("span", { class: "hint", role: "status" });
  const send = async () => {
    try {
      await sendEdit(ctx, "review", "review:changes", drafts);
      await save([]);
      note.textContent = waitingText(data);
    } catch (e) {
      toast(e.message || "Not sent. Try again.");
    }
  };
  const sendBtn = h("button", { class: "btn pri", type: "button", disabled: !drafts.length, onclick: () => {
    const inplace = drafts.filter((d) => d.mode === "inplace");
    if (!inplace.length) { send(); return; }
    ctx.openDialog("inplace", { project: card(data).project, timelines: inplace.map((d) => d.timeline || "?"),
      onInPlace: send,
      onNew: () => { drafts.forEach((d) => { d.mode = "new"; }); send(); } });
  } }, "Send changes");
  return h("section", { class: "card" }, h("h3", {}, "Your changes"),
    drafts.length ? h("ol", { class: "drafts" }, drafts.map((d, i) => h("li", {},
      h("span", {}, d.text), h("span", { class: "hint" }, ` · ${d.timeline || "timeline?"} · ${d.mode === "new" ? "new timeline" : "in place"}`),
      h("button", { class: "btn sm ghost", type: "button", "aria-label": `Remove change ${i + 1}`,
        onclick: () => save(drafts.filter((_, j) => j !== i)) }, "Remove")))) : h("p", { class: "hint" }, "No changes listed yet."),
    h("div", { class: "stack", style: "margin-top:10px" },
      h("label", { class: "lbl", for: "rv-text" }, "New change"), text,
      h("div", { class: "row" }, h("label", { class: "sr", for: "rv-tl" }, "Timeline"), tl,
        h("label", { class: "sr", for: "rv-mode" }, "In place or new timeline"), mode, add)),
    h("div", { class: "row", style: "margin-top:12px" }, sendBtn,
      pendingFor(data, "review:changes").length ? pendingChip() : null, note));
}

export function render(root, data, ctx) {
  const out = outputsOf(data, "review");
  stepPage(root, "review", data, ctx, {
    you: "Review the project in CapCut yourself. Edit it there, or list the changes here and Claude makes them.",
    body: () => [
      isTable(out.changes) ? null : h("section", { class: "card" }, h("h3", {}, "Change list"), h("p", { class: "hint" }, "Changes Claude is making show here.")),
      ...outputTables(ctx, data, "review", { only: (k) => k === "changes" }),
      draftsCard(ctx, data),
      ...outputTables(ctx, data, "review", { skip: ["changes"] }),  // e.g. "edits": your own CapCut edits (edit_diff)
      h("section", { class: "card" }, h("div", { class: "row spread" }, h("div", {}, h("h3", { style: "margin:0" }, "All good?"),
        h("p", { class: "hint" }, "When you're happy with every timeline, Claude moves on to captions.")),
      actionButton(ctx, data, "review", "review:done", "I'm happy, go to captions", { primary: true }))),
    ],
  });
}
