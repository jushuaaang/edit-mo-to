// Clips (step 7, the editor's): the clips folder, "Check clips" (an action: Claude runs qc_clips.py), a row per
// checked clip (PASS / FLAG). FLAG rows open the contact sheet dialog, with Copy prompt when the clip's match name
// is a step-6 prompt id. Gate: regenerate real failures.
// No "missing" rows: a qc_clips report covers only the batch it checked (new files), and its expected names come
// from expected.json, which the GUI doesn't get, so "no clip matched this prompt" can't be told apart from
// "that clip was checked in an earlier batch".
// Generate for me (only where /api/job says generate: true): a "Generate clip" row per step-6 prompt with a real prompt,
// an `action` "generate:clips:<prompt id>"; "Clip in folder" only once a video file named <prompt id> or <prompt id>_…
// is in the clips folder (the server's `clip_files`).
import { h, table, pendingChip, stepTitle } from "../ui.js";
import { t, label } from "../words.js";
import { stepPage, textInput, outputsOf, outputTables, isTable, actionButton, card, lastInput, pendingFor,
  promptsById, promptText, generateButton } from "../steppage.js";

/** The step-6 prompt row for a clip: by its match name (qc_clips' expected name), else that name's "V01" part. */
function promptFor(byId, r) {
  const name = typeof r.match === "string" ? r.match : "";
  return byId.get(name) || byId.get(name.split("_")[0]) || null;
}

const clipsFolder = (ctx, data) => textInput(ctx, data, "clips", "clips_folder", t("clips.folder"), { mono: true,
  placeholder: `${ctx.folder}/clips`, hint: t("clips.folder_hint") });

function clipsCard(ctx, data, tb) {
  const prompts = promptsById(data);
  return table(tb, ctx, { words: { ok: t("clips.pass"), err: t("clips.flag") }, actions: (r) => {
    const pend = pendingFor(data, `clips:${r.id}`).length ? pendingChip() : null;
    if (r.status === "err") {
      return h("span", { class: "row" }, h("button", { class: "btn sm", type: "button",
        onclick: () => ctx.openDialog("contact", { row: r, prompt: promptFor(prompts, r) }) }, t("clips.contact")), pend);
    }
    return pend;
  } });
}

/** Is a clip for this prompt id in the clips folder? Its file is named "<id>" or "<id>_<anything>" (qc_clips names). */
function clipThere(data, id) {
  const k = String(id).toLowerCase();
  const files = Array.isArray(data?.clip_files) ? data.clip_files : [];
  return files.some((f) => {
    const stem = String(f).replace(/\.[^.]+$/, "").toLowerCase();
    return stem === k || stem.startsWith(`${k}_`);
  });
}

function generateCard(ctx, data) {
  if (data?.generate !== true) return null;
  const rows = [...promptsById(data).values()].filter((r) => promptText(r));
  if (!rows.length) return null;
  return h("section", { class: "card" }, h("h3", {}, t("gen.h")), h("p", { class: "hint" }, t("gen.p")),
    h("ul", { class: "files genlist" }, rows.map((r) => h("li", {}, h("span", {}, label(String(r.id), data)),
      generateButton(ctx, data, "clips", String(r.id), { label: t("gen.clip"), done: clipThere(data, r.id),
        doneLabel: t("gen.clip_saved") })))));
}

export function render(root, data, ctx) {
  const out = outputsOf(data, "clips");
  const gen = card(data).generator;
  stepPage(root, "clips", data, ctx, {
    you: t(gen ? "clips.you_gen" : "clips.you", { gen, step: stepTitle("prompts") }),
    early: () => [clipsFolder(ctx, data), generateCard(ctx, data)],
    body: () => [
      generateCard(ctx, data),
      h("section", { class: "card" }, clipsFolder(ctx, data),
        h("div", { class: "row", style: "margin-top:12px" }, actionButton(ctx, data, "clips", "clips:check", t("clips.check"), {
          primary: true, value: () => lastInput(data, "clips:clips_folder")?.value || card(data).clips_folder || null }))),
      isTable(out.clips) ? clipsCard(ctx, data, out.clips)
        : h("section", { class: "card" }, h("h3", {}, t("clips.check_h")), h("p", { class: "hint" }, t("clips.check_empty"))),
      ...outputTables(ctx, data, "clips", { skip: ["clips"] }),
    ],
  });
}
