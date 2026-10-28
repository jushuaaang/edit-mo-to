// Export (step 12, the editor's): the red "Delete the TEMP_EN_delete_me track before export" banner while any timeline
// still has it (a fresh read-only /api/temp-en check, naming the timelines), the brief's export settings,
// "I've exported, run the learning step" (an action), and the learning step's proposals (the `learn` dialog).
import { h, helpTip } from "../ui.js";
import { t } from "../words.js";
import { stepPage, outputsOf, isTable, actionButton, card } from "../steppage.js";

const RECHECK_MS = 10000;
const EXPORTISH = /export|fps|1080|9:16|16:9|4:5|resolution|format|bitrate|codec|length|duration|aspect/i;
let tempEn = { key: null, at: 0, timelines: null, error: null, checking: false };  // last check, so a re-render doesn't recheck at once

/** The CapCut project folder for the job: card.project as a full path, or under capcut_drafts. */
async function projectPath(ctx) {
  const p = String(ctx.data?.job?.card?.project || "");
  if (!p) return null;
  if (/^([a-zA-Z]:)?[\\/]/.test(p)) return p;
  const s = await ctx.api("/api/settings");
  return s?.paths?.capcut_drafts ? `${String(s.paths.capcut_drafts).replace(/[\\/]+$/, "")}/${p}` : null;
}

/** The TEMP_EN banner. A fresh read-only /api/temp-en check runs whenever the project is known, whatever the card says.
 *  When it can't run (no project on the card, or the check failed) and TEMP_EN was ever on, the page never shows nothing:
 *  the card's red banner (on / partial), or "Could not check" (removed). An empty check result is the only "clean". */
function tempEnBanner(ctx, data) {
  const box = h("div", { "aria-live": "polite" });
  const te = String(card(data).temp_en || "");
  const onCard = te === "on" || te.startsWith("partial:");
  const everOn = onCard || te === "removed";
  const project = String(card(data).project || "");
  const key = `${ctx.folder}|${project}`;
  const cardBanner = (why) => h("div", { class: "banner err", role: "alert" },
    h("b", {}, t("export.delete_h"), helpTip("temp_en")),
    h("span", {}, `${te.startsWith("partial:") ? t("export.still_on", { names: te.slice(8) }) : t("export.card_says")} ${why}`));
  const cantCheck = (why) => h("div", { class: "banner wait", role: "alert" },
    h("b", {}, t("export.cant_check_h")), h("span", {}, why));
  const draw = () => {
    const why = tempEn.error ? t("export.cant_check_err", { err: tempEn.error }) : t("export.no_project");
    let node = null;
    if (tempEn.timelines?.length) {
      node = h("div", { class: "banner err", role: "alert" }, h("b", {}, t("export.delete_h"), helpTip("temp_en")),
        h("span", {}, t("export.still_on", { names: tempEn.timelines.join(", ") })));
    } else if (tempEn.timelines) {
      node = everOn ? h("div", { class: "banner ok", role: "status" }, h("span", {}, t("export.clean"))) : null;
    } else if (tempEn.checking) {
      node = everOn ? h("div", { class: "banner wait", role: "status" }, h("span", {}, t("export.checking"))) : null;
    } else if (onCard) {
      node = cardBanner(why);
    } else if (everOn || tempEn.error) {
      node = cantCheck(why);
    }
    box.replaceChildren(...[node].filter(Boolean));
  };
  if (tempEn.key === key && !tempEn.checking && Date.now() - tempEn.at < RECHECK_MS) { draw(); return box; }
  if (tempEn.key !== key || !tempEn.checking) {
    tempEn = { key, at: Date.now(), timelines: null, error: null, checking: true };
    (async () => {
      let next;
      try {
        const path = project ? await projectPath(ctx) : null;
        if (!path) next = { timelines: null, error: project ? t("export.no_drafts") : null };
        else {
          const r = await ctx.api(`/api/temp-en?project=${encodeURIComponent(path)}`);
          next = Array.isArray(r?.timelines) ? { timelines: r.timelines, error: null } : { timelines: null, error: t("export.no_answer") };
        }
      } catch (e) {
        next = { timelines: null, error: e.message || t("export.unknown") };
      }
      if (tempEn.key === key) tempEn = { key, at: Date.now(), checking: false, ...next };
      if (box.isConnected) draw();
    })();
  }
  draw();
  return box;
}

function settingsCard(data) {
  const rules = data?.outputs?.brief?.checklist?.rules || [];
  const shown = rules.filter((r) => EXPORTISH.test(String(r.rule ?? "")));
  return h("section", { class: "card" }, h("h3", {}, t("export.settings_h")),
    (shown.length ? shown : rules).length ? h("ul", { class: "files" }, (shown.length ? shown : rules).map((r) => h("li", {},
      h("span", {}, String(r.rule ?? "")), h("span", { class: "hint" }, String(r.source ?? "")))))
      : h("p", { class: "hint" }, t("export.default")));
}

export function render(root, data, ctx) {
  const learn = outputsOf(data, "export").learn;
  stepPage(root, "export", data, ctx, {
    you: t("export.you"),
    body: () => [
      tempEnBanner(ctx, data),
      settingsCard(data),
      h("section", { class: "card" }, h("h3", {}, t("export.done_h")),
        h("p", { class: "hint" }, t("export.done_p")),
        h("div", { class: "row", style: "margin-top:10px" },
          actionButton(ctx, data, "export", "export:learn", t("export.learn"), { primary: true }),
          isTable(learn) && learn.rows.length ? h("button", { class: "btn", type: "button",
            onclick: () => ctx.openDialog("learn", { table: learn }) }, t("export.review_learned", { n: learn.rows.length })) : null)),
    ],
  });
}
