// Voiceover (step 4, the editor's): VO file drop (one file, or one per hook/body), "Reuse an older VO" (dialog),
// the script language and the --lang it means. Gates: the VO file; the older-VO spans.
import { h, helpTip } from "../ui.js";
import { stepPage, uploadInput, outputsOf, outputTables, card, openGate } from "../steppage.js";

/** "Spanish (es)" -> "es"; else the script output's lang. */
function langCode(data) {
  const m = /\(([a-z]{2,3}(?:-[A-Za-z]{2})?)\)/.exec(String(card(data).language || ""));
  return m ? m[1] : outputsOf(data, "script").script?.lang || null;
}

function langCard(data) {
  const lang = card(data).language;
  const code = langCode(data);
  return h("section", { class: "card" }, h("h3", {}, "Script language"),
    lang || code ? h("p", {}, lang || code, code ? h("span", { class: "hint" }, " · Claude times the VO with ",
      h("span", { class: "mono" }, `--lang ${code}`)) : null)
      : h("p", { class: "hint" }, "Set at the brief."));
}

export function render(root, data, ctx) {
  const where = `${ctx.folder}/vo/`;
  stepPage(root, "voiceover", data, ctx, {
    you: `Make the voiceover yourself (ElevenLabs), as one file or one per hook/body, then drop it here. It's copied to ${where}`,
    early: () => [uploadInput(ctx, data, "voiceover", "vo", "Voiceover file(s)")],
    body: () => [
      h("section", { class: "card" }, h("h3", {}, "Voiceover file", helpTip("vo")),
        uploadInput(ctx, data, "voiceover", "vo", "Voiceover file(s)"),
        h("div", { class: "row", style: "margin-top:12px" },
          h("button", { class: "btn", type: "button",
            onclick: () => ctx.openDialog("oldvo", { gate: openGate(data, "voiceover"), data }) }, "Reuse an older VO"),
          h("span", { class: "hint" }, "Saves credits: Claude transcribes an older VO and you pick the sentences."))),
      langCard(data),
      ...outputTables(ctx, data, "voiceover", { skip: ["oldvo"] }),
    ],
  });
}
