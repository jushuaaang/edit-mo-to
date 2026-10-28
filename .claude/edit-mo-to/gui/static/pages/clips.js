// Clips (step 7, the editor's): the clips folder, "Check clips" (an action: Claude runs qc_clips.py), a row per
// checked clip (PASS / FLAG). FLAG rows open the contact sheet dialog, with Copy prompt when the clip's match name
// is a step-6 prompt id. Gate: regenerate real failures.
// No "missing" rows: a qc_clips report covers only the batch it checked (new files), and its expected names come
// from expected.json, which the GUI doesn't get, so "no clip matched this prompt" can't be told apart from
// "that clip was checked in an earlier batch".
import { h, table, pendingChip } from "../ui.js";
import { stepPage, textInput, outputsOf, outputTables, isTable, actionButton, card, lastInput, pendingFor,
  promptsById } from "../steppage.js";

/** The step-6 prompt row for a clip: by its match name (qc_clips' expected name), else that name's "V01" part. */
function promptFor(byId, r) {
  const name = typeof r.match === "string" ? r.match : "";
  return byId.get(name) || byId.get(name.split("_")[0]) || null;
}

const clipsFolder = (ctx, data) => textInput(ctx, data, "clips", "clips_folder", "Clips folder", { mono: true,
  placeholder: `${ctx.folder}/clips`, hint: "The folder where you save the generated clips." });

function clipsCard(ctx, data, t) {
  const prompts = promptsById(data);
  return table(t, ctx, { words: { ok: "PASS", err: "FLAG" }, actions: (r) => {
    const pend = pendingFor(data, `clips:${r.id}`).length ? pendingChip() : null;
    if (r.status === "err") {
      return h("span", { class: "row" }, h("button", { class: "btn sm", type: "button",
        onclick: () => ctx.openDialog("contact", { row: r, prompt: promptFor(prompts, r) }) }, "Contact sheet"), pend);
    }
    return pend;
  } });
}

export function render(root, data, ctx) {
  const out = outputsOf(data, "clips");
  const gen = card(data).generator;
  stepPage(root, "clips", data, ctx, {
    you: `Generate the clips yourself${gen ? ` in ${gen}` : ""} from the prompts on B-roll & prompts, save them in the clips folder, then press Check clips.`,
    early: () => [clipsFolder(ctx, data)],
    body: () => [
      h("section", { class: "card" }, clipsFolder(ctx, data),
        h("div", { class: "row", style: "margin-top:12px" }, actionButton(ctx, data, "clips", "clips:check", "Check clips", {
          primary: true, value: () => lastInput(data, "clips:clips_folder")?.value || card(data).clips_folder || null }))),
      isTable(out.clips) ? clipsCard(ctx, data, out.clips)
        : h("section", { class: "card" }, h("h3", {}, "Clip check"), h("p", { class: "hint" }, "Results show here after Check clips.")),
      ...outputTables(ctx, data, "clips", { skip: ["clips"] }),
    ],
  });
}
