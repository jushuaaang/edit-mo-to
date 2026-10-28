// Music (step 11): the Suno prompt from Claude (parts of max 18 s, Copy, crossfade notes) or the editor's own track,
// the music file drop (music/), which timelines. Gates: source; timelines; quit CapCut.
import { h } from "../ui.js";
import { stepPage, choiceInput, uploadInput, outputsOf, outputTables, isTable, promptText, copyButton, lastInput } from "../steppage.js";

const SOURCES = [["suno", "Suno prompt from Claude"], ["own", "My own no-copyright track"]];

const source = (ctx, data) => choiceInput(ctx, data, "music", "source", "Music source", SOURCES);
const drop = (ctx, data) => uploadInput(ctx, data, "music", "music", "Music file");

function sunoCard(t) {
  return h("section", { class: "card" }, h("h3", {}, t.title || "Suno prompt"),
    h("p", { class: "hint" }, "Parts of at most 18 s each; generate them in order and crossfade as the notes say."),
    h("ul", { class: "prompts" }, t.rows.map((r) => h("li", {},
      h("div", {}, h("span", { class: "mono" }, String(r.id ?? "")), " ", h("span", { class: "hint" }, (r.cells || []).slice(1).join(" · ")),
        h("pre", { class: "prompt" }, promptText(r))),
      copyButton(promptText(r), "Copy")))));
}

export function render(root, data, ctx) {
  const out = outputsOf(data, "music");
  const where = `${ctx.folder}/music/`;
  const own = lastInput(data, "music:source")?.value === "own";
  stepPage(root, "music", data, ctx, {
    you: own ? `Pick a no-copyright track (YouTube Audio Library or similar) and drop it here. It's copied to ${where}`
      : `Make the track in Suno with Claude's prompt, then drop the file here. It's copied to ${where}`,
    early: () => [source(ctx, data), drop(ctx, data)],
    body: () => [
      h("section", { class: "card" }, source(ctx, data)),
      isTable(out.suno) ? sunoCard(out.suno) : null,
      h("section", { class: "card" }, drop(ctx, data)),
      ...outputTables(ctx, data, "music", { skip: ["suno"] }),
    ],
  });
}
