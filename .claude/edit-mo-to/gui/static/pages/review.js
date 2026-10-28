// Review (step 9, the editor's): the CapCut banner once per round (from the gate), the change list (change, timeline,
// in place / new timeline, status), "Send changes", "I'm happy, go to captions", and the editor's own edits found by
// edit_diff. Gates: which timeline; in place or new; quit CapCut.
// Changes not yet sent are drafts in gui.json (`review_drafts`); "Send changes" is one `edit` event (target
// "review:changes"); a change in place first shows the `inplace` dialog (where the backup goes).
import { h, pendingChip, toast, helpTip } from "../ui.js";
import { t } from "../words.js";
import { stepPage, outputsOf, outputTables, isTable, actionButton, pendingFor, sendEdit, timelines, card, waitingText } from "../steppage.js";

const MODES = [["inplace", "review.inplace"], ["new", "review.new"]];  // value, word

function draftsCard(ctx, data) {
  const drafts = Array.isArray(data?.gui?.review_drafts) ? data.gui.review_drafts : [];
  const tls = timelines(data);
  const text = h("textarea", { class: "f", rows: "2", id: "rv-text", "data-key": "review:text",
    placeholder: t("review.ph") });
  const tl = h("select", { class: "f", id: "rv-tl", "data-key": "review:tl" },
    h("option", { value: "" }, t("review.which")), tls.map((n) => h("option", { value: n }, n)), h("option", { value: "all" }, t("review.all")));
  const mode = h("select", { class: "f", id: "rv-mode", "data-key": "review:mode" }, MODES.map(([v, k]) => h("option", { value: v }, t(k))));
  const save = (list) => ctx.saveGui({ review_drafts: list.length ? list : null }).catch((e) => toast(e.message || t("common.not_saved")));
  const add = h("button", { class: "btn", type: "button", onclick: () => {
    if (!text.value.trim()) { text.focus(); return; }
    const draft = { text: text.value.trim(), timeline: tl.value || null, mode: mode.value };
    text.value = "";
    save([...drafts, draft]);
  } }, t("review.add"));
  const note = h("span", { class: "hint", role: "status" });
  const send = async () => {
    try {
      await sendEdit(ctx, "review", "review:changes", drafts);
      await save([]);
      note.textContent = waitingText(data);
    } catch (e) {
      toast(e.message || t("common.not_sent"));
    }
  };
  const sendBtn = h("button", { class: "btn pri", type: "button", disabled: !drafts.length, onclick: () => {
    const inplace = drafts.filter((d) => d.mode === "inplace");
    if (!inplace.length) { send(); return; }
    ctx.openDialog("inplace", { project: card(data).project, timelines: inplace.map((d) => d.timeline || "?"),
      onInPlace: send,
      onNew: () => { drafts.forEach((d) => { d.mode = "new"; }); send(); } });
  } }, t("review.send"));
  return h("section", { class: "card" }, h("h3", {}, t("review.h")),
    drafts.length ? h("ol", { class: "drafts" }, drafts.map((d, i) => h("li", {},
      h("span", {}, d.text), h("span", { class: "hint" }, t("review.item", { timeline: d.timeline || t("review.tl_unknown"),
        mode: t(d.mode === "new" ? "review.mode_new" : "review.mode_inplace") })),
      h("button", { class: "btn sm ghost", type: "button", "aria-label": t("review.remove_label", { n: i + 1 }),
        onclick: () => save(drafts.filter((_, j) => j !== i)) }, t("review.remove"))))) : h("p", { class: "hint" }, t("review.none")),
    h("div", { class: "stack", style: "margin-top:10px" },
      h("label", { class: "lbl", for: "rv-text" }, t("review.new_change")), text,
      h("p", { class: "hint words" }, t("help.row"), h("span", { class: "word" }, t("word.timeline"), helpTip("timeline"))),
      h("div", { class: "row" }, h("label", { class: "sr", for: "rv-tl" }, t("review.timeline")), tl,
        h("label", { class: "sr", for: "rv-mode" }, t("review.mode_label")), mode, add)),
    h("div", { class: "row", style: "margin-top:12px" }, sendBtn,
      pendingFor(data, "review:changes").length ? pendingChip() : null, note));
}

export function render(root, data, ctx) {
  const out = outputsOf(data, "review");
  stepPage(root, "review", data, ctx, {
    you: t("review.you"),
    body: () => [
      isTable(out.changes) ? null : h("section", { class: "card" }, h("h3", {}, t("review.list_h")), h("p", { class: "hint" }, t("review.list_p"))),
      ...outputTables(ctx, data, "review", { only: (k) => k === "changes" }),
      draftsCard(ctx, data),
      ...outputTables(ctx, data, "review", { skip: ["changes"] }),  // e.g. "edits": your own CapCut edits (edit_diff)
      h("section", { class: "card" }, h("div", { class: "row spread" }, h("div", {}, h("h3", { style: "margin:0" }, t("review.done_h")),
        h("p", { class: "hint" }, t("review.done_p"))),
      actionButton(ctx, data, "review", "review:done", t("review.done"), { primary: true }))),
    ],
  });
}
