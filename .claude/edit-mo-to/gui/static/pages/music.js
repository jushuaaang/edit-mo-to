// Music (step 11): the Suno prompt from Claude (parts of max 18 s, Copy, crossfade notes) or the editor's own track,
// the music file drop (music/), which timelines. Gates: source; timelines; quit CapCut.
import { h } from "../ui.js";
import { t, parts } from "../words.js";
import { stepPage, choiceInput, uploadInput, outputsOf, outputTables, isTable, promptText, copyButton, lastInput,
  folderWord } from "../steppage.js";

const SOURCES = [["suno", "music.suno"], ["own", "music.own"]];  // value, word

const source = (ctx, data) => choiceInput(ctx, data, "music", "source", t("music.source"), SOURCES.map(([v, k]) => [v, t(k)]));
const drop = (ctx, data) => uploadInput(ctx, data, "music", "music", t("music.file"));

function sunoCard(tb) {
  return h("section", { class: "card" }, h("h3", {}, tb.title || t("music.suno_h")),
    h("p", { class: "hint" }, t("music.suno_p")),
    h("ul", { class: "prompts" }, tb.rows.map((r) => h("li", {},
      h("div", {}, h("span", { class: "mono" }, String(r.id ?? "")), " ", h("span", { class: "hint" }, (r.cells || []).slice(1).join(" · ")),
        promptText(r) ? h("pre", { class: "prompt" }, promptText(r)) : null),
      promptText(r) ? copyButton(promptText(r), t("common.copy")) : null))));
}

export function render(root, data, ctx) {
  const out = outputsOf(data, "music");
  const own = lastInput(data, "music:source")?.value === "own";
  stepPage(root, "music", data, ctx, {
    you: parts(own ? "music.you_own" : "music.you_suno", { where: folderWord(ctx, "music") }),
    early: () => [source(ctx, data), drop(ctx, data)],
    body: () => [
      h("section", { class: "card" }, source(ctx, data)),
      isTable(out.suno) ? sunoCard(out.suno) : null,
      h("section", { class: "card" }, drop(ctx, data)),
      ...outputTables(ctx, data, "music", { skip: ["suno"] }),
    ],
  });
}
