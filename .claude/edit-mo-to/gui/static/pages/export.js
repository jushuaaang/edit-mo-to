// Export (step 12, the editor's): the red "Delete the TEMP_EN_delete_me track before export" banner while any timeline
// still has it (a fresh read-only /api/temp-en check, naming the timelines), the brief's export settings,
// "I've exported, run the learning step" (an action), and the learning step's proposals (the `learn` dialog).
import { h } from "../ui.js";
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
  const t = String(card(data).temp_en || "");
  const onCard = t === "on" || t.startsWith("partial:");
  const everOn = onCard || t === "removed";
  const project = String(card(data).project || "");
  const key = `${ctx.folder}|${project}`;
  const cardBanner = (why) => h("div", { class: "banner err", role: "alert" },
    h("b", {}, "Delete the TEMP_EN_delete_me track before export"),
    h("span", {}, `${t.startsWith("partial:") ? `Still on: ${t.slice(8)}` : "The job card says it is still on."} ${why}`));
  const cantCheck = (why) => h("div", { class: "banner wait", role: "alert" },
    h("b", {}, "Could not check: delete TEMP_EN_delete_me before export if present"), h("span", {}, why));
  const draw = () => {
    const why = tempEn.error ? `Couldn't check the project (${tempEn.error}).` : "Couldn't check: no CapCut project on the job card yet.";
    let node = null;
    if (tempEn.timelines?.length) {
      node = h("div", { class: "banner err", role: "alert" }, h("b", {}, "Delete the TEMP_EN_delete_me track before export"),
        h("span", {}, `Still on: ${tempEn.timelines.join(", ")}`));
    } else if (tempEn.timelines) {
      node = everOn ? h("div", { class: "banner ok", role: "status" }, h("span", {}, "Checked the project: no TEMP_EN_delete_me track left.")) : null;
    } else if (tempEn.checking) {
      node = everOn ? h("div", { class: "banner wait", role: "status" }, h("span", {}, "Checking the project for the TEMP_EN_delete_me track…")) : null;
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
        if (!path) next = { timelines: null, error: project ? "the CapCut drafts folder isn't set in Settings" : null };
        else {
          const r = await ctx.api(`/api/temp-en?project=${encodeURIComponent(path)}`);
          next = Array.isArray(r?.timelines) ? { timelines: r.timelines, error: null } : { timelines: null, error: "no answer" };
        }
      } catch (e) {
        next = { timelines: null, error: e.message || "unknown error" };
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
