// Export (step 12, the editor's): the red "Delete the TEMP_EN_delete_me track before export" banner while any timeline
// still has it (a fresh read-only /api/temp-en check, naming the timelines), the brief's export settings,
// "I've exported, run the learning step" (an action), and the learning step's proposals (the `learn` dialog).
import { h } from "../ui.js";
import { stepPage, outputsOf, isTable, actionButton, card } from "../steppage.js";

const RECHECK_MS = 10000;
const EXPORTISH = /export|fps|1080|9:16|16:9|4:5|resolution|format|bitrate|codec|length|duration|aspect/i;
let tempEn = { key: null, at: 0, timelines: null, error: null };  // last check, so a re-render doesn't recheck at once

/** The CapCut project folder for the job: card.project as a full path, or under capcut_drafts. */
async function projectPath(ctx) {
  const p = String(ctx.data?.job?.card?.project || "");
  if (!p) return null;
  if (/^([a-zA-Z]:)?[\\/]/.test(p)) return p;
  const s = await ctx.api("/api/settings");
  return s?.paths?.capcut_drafts ? `${String(s.paths.capcut_drafts).replace(/[\\/]+$/, "")}/${p}` : null;
}

function tempEnBanner(ctx, data) {
  const box = h("div", { "aria-live": "polite" });
  const t = String(card(data).temp_en || "");
  if (t === "removed" || t === "off" || (!t && !card(data).project)) return box;
  const draw = () => {
    if (tempEn.error) box.replaceChildren(h("div", { class: "banner wait" }, h("span", {}, `Could not check the project for the TEMP_EN track: ${tempEn.error}`)));
    else if (tempEn.timelines?.length) {
      box.replaceChildren(h("div", { class: "banner err", role: "alert" }, h("b", {}, "Delete the TEMP_EN_delete_me track before export"),
        h("span", {}, `Still on: ${tempEn.timelines.join(", ")}`)));
    } else box.replaceChildren();
  };
  const key = String(card(data).project || "");
  if (tempEn.key === key && Date.now() - tempEn.at < RECHECK_MS) { draw(); return box; }
  (async () => {
    try {
      const path = await projectPath(ctx);
      if (!path) { tempEn = { key, at: Date.now(), timelines: null, error: null }; return; }
      const r = await ctx.api(`/api/temp-en?project=${encodeURIComponent(path)}`);
      tempEn = { key, at: Date.now(), timelines: r?.timelines || [], error: null };
    } catch (e) {
      tempEn = { key, at: Date.now(), timelines: null, error: e.message || "unknown error" };
    }
    if (box.isConnected) draw();
  })();
  return box;
}

function settingsCard(data) {
  const rules = data?.outputs?.brief?.checklist?.rules || [];
  const shown = rules.filter((r) => EXPORTISH.test(String(r.rule ?? "")));
  return h("section", { class: "card" }, h("h3", {}, "Export settings from the brief"),
    (shown.length ? shown : rules).length ? h("ul", { class: "files" }, (shown.length ? shown : rules).map((r) => h("li", {},
      h("span", {}, String(r.rule ?? "")), h("span", { class: "hint" }, String(r.source ?? "")))))
      : h("p", { class: "hint" }, "Default: 9:16, 1080×1920, 30 fps."));
}

export function render(root, data, ctx) {
  const learn = outputsOf(data, "export").learn;
  stepPage(root, "export", data, ctx, {
    you: "Export each timeline in CapCut yourself, with the settings below.",
    body: () => [
      tempEnBanner(ctx, data),
      settingsCard(data),
      h("section", { class: "card" }, h("h3", {}, "Done exporting?"),
        h("p", { class: "hint" }, "Claude then runs the learning step: it proposes preferences from this video, and you save or decline each."),
        h("div", { class: "row", style: "margin-top:10px" },
          actionButton(ctx, data, "export", "export:learn", "I've exported, run the learning step", { primary: true }),
          isTable(learn) && learn.rows.length ? h("button", { class: "btn", type: "button",
            onclick: () => ctx.openDialog("learn", { table: learn }) }, `Review what Claude learned (${learn.rows.length})`) : null)),
    ],
  });
}
