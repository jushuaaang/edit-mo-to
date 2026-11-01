// Voiceover (step 4, the editor's): VO file drop (one file, or one per hook/body), "Reuse an older VO" (dialog),
// the script language and the --lang it means. Gates: the VO file; the older-VO spans.
// Generate for me (only where /api/job says generate: true): "Generate voiceover", an `action` "generate:voiceover:all"
// (Claude shows the credits and asks first: the gate's `vo_make_ok` confirm, shown as Make it / Don't make it; the
// page only sends the answer); "Voiceover in vo/" only once a file in vo/ is newer than the click.
import { h, helpTip, copyButton } from "../ui.js";
import { t, parts } from "../words.js";
import { stepPage, uploadInput, outputsOf, outputTables, card, openGate, generateButton, gateAsks, pendingFor,
  folderWord } from "../steppage.js";

/** "Spanish (es)" -> "es"; else the script output's lang. */
function langCode(data) {
  const m = /\(([a-z]{2,3}(?:-[A-Za-z]{2})?)\)/.exec(String(card(data).language || ""));
  return m ? m[1] : outputsOf(data, "script").script?.lang || null;
}

function langCard(data) {
  const lang = card(data).language;
  const code = langCode(data);
  return h("section", { class: "card" }, h("h3", {}, t("vo.lang_h")),
    lang || code ? h("p", {}, lang || code, code ? h("span", { class: "hint" }, t("vo.times_with"), " ",
      h("span", { class: "mono" }, `--lang ${code}`)) : null)
      : h("p", { class: "hint" }, t("vo.set_at_brief")));
}

/** The approved script, ready to paste into ElevenLabs: the hooks (H1, H2, …) each on their own, since each hook can be
 *  its own voiceover file, and the body (every other line, in order) as one block; plus "hook 1 + body" in one go for
 *  a single file. Copy buttons only: the text is the script exactly as approved (never translated). */
function scriptCard(data) {
  const lines = (outputsOf(data, "script").script?.lines || []).filter((l) => l && String(l.text || "").trim());
  if (!lines.length) return null;
  const hooks = lines.filter((l) => /^H\d*$/i.test(String(l.id || "")));
  const body = lines.filter((l) => !hooks.includes(l));
  const bodyText = body.map((l) => String(l.text).trim()).join("\n");
  const block = (label, text) => h("div", { class: "vo-line" },
    h("div", { class: "row spread" }, h("b", {}, label), copyButton(text)),
    h("p", { class: "vo-text" }, text));
  return h("section", { class: "card" }, h("h3", {}, t("vo.script_h")), h("p", { class: "hint" }, t("vo.script_p")),
    hooks.length ? h("div", { class: "stack" }, h("div", { class: "lbl" }, t("vo.hooks")),
      ...hooks.map((l, i) => block(t("vo.hook_n", { n: i + 1, id: l.id }), String(l.text).trim()))) : null,
    bodyText ? h("div", { class: "stack", style: "margin-top:12px" }, h("div", { class: "lbl" }, t("vo.body")),
      block(t("vo.body_lines", { n: body.length }), bodyText)) : null,
    hooks.length && bodyText ? h("div", { class: "row", style: "margin-top:12px" },
      copyButton(`${String(hooks[0].text).trim()}\n${bodyText}`, t("vo.copy_all")),
      h("span", { class: "hint" }, t("vo.copy_all_hint"))) : null);
}

/** The newest file in vo/ (ms; the server's vo_mtimes), or null: "Voiceover in vo/" only for a file newer than the click. */
function newestVo(data) {
  const times = Object.values(data?.vo_mtimes || {}).filter((n) => typeof n === "number" && Number.isFinite(n));
  return times.length ? Math.max(...times) / 1e6 : null;
}

/** early: the click came before the Voiceover step, so Claude keeps it until then ("Saved for later"). */
const generateVo = (ctx, data, early = false) => generateButton(ctx, data, "voiceover", "all", { label: t("gen.voiceover"),
  vo: true, early, doneAt: newestVo(data), doneLabel: t("gen.vo_saved") });

export function render(root, data, ctx) {
  // "Make it?" is open (or a Generate voiceover click is still pending): the box says Claude is asking first, and no
  // second Generate voiceover button sits under the question (a double press would ask twice).
  const asking = gateAsks(data, "voiceover", "vo_make_ok");
  const genPending = pendingFor(data, "generate:voiceover:all").length > 0;
  stepPage(root, "voiceover", data, ctx, {
    you: asking ? t("vo.you_ask") : genPending ? t("vo.you_gen") : parts("vo.you", { where: folderWord(ctx, "vo") }),
    labels: { vo_make_ok: { yes: t("vo.make_it"), no: t("vo.dont_make") } },
    early: () => [uploadInput(ctx, data, "voiceover", "vo", t("vo.files")), generateVo(ctx, data, true)],
    body: () => [
      scriptCard(data),
      h("section", { class: "card" }, h("h3", {}, t("vo.file_h"), helpTip("vo")),
        uploadInput(ctx, data, "voiceover", "vo", t("vo.files")),
        asking ? null : generateVo(ctx, data),
        h("div", { class: "row", style: "margin-top:12px" },
          h("button", { class: "btn", type: "button",
            onclick: () => ctx.openDialog("oldvo", { gate: openGate(data, "voiceover"), data }) }, t("vo.reuse")),
          h("span", { class: "hint" }, t("vo.reuse_hint")))),
      langCard(data),
      ...outputTables(ctx, data, "voiceover", { skip: ["oldvo"] }),
    ],
  });
}
