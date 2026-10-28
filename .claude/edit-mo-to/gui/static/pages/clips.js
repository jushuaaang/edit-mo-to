// Clips (step 7, the editor's): the clips folder, "Check clips" (an action: Claude runs qc_clips.py), a row per
// clip (PASS / FLAG / missing). FLAG rows open the contact sheet dialog; missing rows have Copy prompt.
// Gate: regenerate real failures.
import { h, table, pendingChip } from "../ui.js";
import { stepPage, textInput, outputsOf, outputTables, isTable, actionButton, card, lastInput, pendingFor, promptText,
  copyButton } from "../steppage.js";

const missing = (r) => r.status === "you" || (r.cells || []).some((c) => /^missing$/i.test(String(c)));

/** The prompt rows of step 6, by id, for "Copy prompt" on missing clips. */
function promptRows(data) {
  const by = new Map();
  for (const t of Object.values(data?.outputs?.prompts || {})) if (isTable(t)) t.rows.forEach((r) => by.set(String(r.id), r));
  return by;
}

const clipsFolder = (ctx, data) => textInput(ctx, data, "clips", "clips_folder", "Clips folder", { mono: true,
  placeholder: `${ctx.folder}/clips`, hint: "The folder where you save the generated clips." });

function clipsCard(ctx, data, t) {
  const prompts = promptRows(data);
  return table(t, ctx, { words: { ok: "PASS", err: "FLAG", you: "Missing" }, actions: (r) => {
    const pend = pendingFor(data, `clips:${r.id}`).length ? pendingChip() : null;
    if (missing(r)) {
      const p = typeof r.prompt === "string" ? r : prompts.get(String(r.id));
      return h("span", { class: "row" }, p ? copyButton(promptText(p), "Copy prompt") : null, pend);
    }
    if (r.status === "err") {
      return h("span", { class: "row" }, h("button", { class: "btn sm", type: "button",
        onclick: () => ctx.openDialog("contact", { row: r, prompt: prompts.get(String(r.id)) }) }, "Contact sheet"), pend);
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
