// Export (step 12, the editor's): the red "Delete the TEMP_EN_delete_me track before export" banner while any timeline
// still has it (a fresh read-only /api/temp-en check, naming the timelines), the brief's export settings,
// "I've exported, run the learning step" or "I've exported, skip the learning step" (actions), and the learning
// step's proposals (the `learn` dialog).
import { h, helpTip, chip, toast } from "../ui.js";
import { t } from "../words.js";
import { stepPage, outputsOf, isTable, actionButton, card, openGate } from "../steppage.js";

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

/** The rules ticked to save while Claude asks (per video): [{id, box, scope}], read by the question bar's Proceed. */
const picks = new Map();
// each rule's tick and where to keep it as the editor left them (`<folder>|<id>`): the page redraws whenever Claude
// updates something, and a redraw must never tick a rule the editor unticked again
const kept = new Map();

/** What Claude learned, on the page (not a pop-up): each proposed rule with its note and where to keep it. While Claude
 *  asks about them, each rule has a "Save this rule" tick (all ticked to start; Select all / none) and the question
 *  bar's Proceed sends one `learn:<id>` per rule with the answer; otherwise each rule has its own Save / Decline. */
function learnCard(ctx, data, learn) {
  const rows = isTable(learn) ? learn.rows : [];
  if (!rows.length) return null;
  const key = String(data?.job?.folder || ctx.folder || "");
  const asking = Boolean(openGate(data, "export"));
  const mine = [];
  const items = rows.map((r) => {
    const id = String(r.id ?? "");
    const text = (r.cells || []).map(String).filter(Boolean).join(" · ");
    const scope = h("select", { class: "f", "aria-label": t("dlg.where_keep", { id }) },
      h("option", { value: "general" }, t("dlg.general")), h("option", { value: "client" }, t("dlg.client_note")));
    if (/client/i.test(text)) scope.value = "client";
    const was = kept.get(`${key}|${id}`);
    if (was) scope.value = was.scope;
    scope.addEventListener("change", () => kept.set(`${key}|${id}`, { ...(kept.get(`${key}|${id}`) || { on: true }), scope: scope.value }));
    if (asking) {
      const box = h("input", { type: "checkbox", checked: was ? was.on : true, "aria-label": t("export.save_this", { id }),
        onchange: () => kept.set(`${key}|${id}`, { on: box.checked, scope: scope.value }) });
      mine.push({ id, box, scope });
      return h("li", {}, h("label", { class: "check learn-pick" }, box, h("span", {}, t("export.save_this_short"))),
        h("div", {}, text), r.note ? h("div", { class: "hint" }, String(r.note)) : null,
        h("div", { class: "row", style: "margin-top:6px" }, scope));
    }
    const state = h("span", { role: "status" });
    const decide = (decision) => async () => {
      try {
        await ctx.send({ type: "answer", step: "export", gate: null, target: `learn:${id}`, value: { decision, scope: scope.value } });
        state.replaceChildren(chip(t(decision === "save" ? "dlg.saved_waiting" : "dlg.declined"), decision === "save" ? "wait" : "mute"));
      } catch (e) {
        toast(e.message || t("common.not_sent"));
      }
    };
    return h("li", {}, h("div", {}, text), r.note ? h("div", { class: "hint" }, String(r.note)) : null,
      h("div", { class: "row", style: "margin-top:6px" }, scope,
        h("button", { class: "btn sm pri", type: "button", onclick: decide("save") }, t("common.save")),
        h("button", { class: "btn sm", type: "button", onclick: decide("decline") }, t("dlg.decline")), state));
  });
  if (asking) picks.set(key, mine);
  const all = asking && rows.length > 1 ? h("button", { class: "linkish", type: "button", onclick: () => {
    const on = !mine.every((x) => x.box.checked);
    mine.forEach((x) => { x.box.checked = on; kept.set(`${key}|${x.id}`, { on, scope: x.scope.value }); });
  } }, t("export.select_all")) : null;
  return h("section", { class: "card" }, h("div", { class: "row spread" }, h("h3", { style: "margin:0" }, t("export.learned_h", { n: rows.length })), all),
    h("p", { class: "hint", style: "margin-top:6px" }, t(asking ? "export.learned_asking" : "dlg.learn_p")),
    h("ol", { class: "learn" }, items));
}

export function render(root, data, ctx) {
  const learn = outputsOf(data, "export").learn;
  const key = String(data?.job?.folder || ctx.folder || "");
  const pressed = (data?.events || []).some((e) => e.type === "action" && (e.target === "export:learn" || e.target === "export:skip-learn"));
  const chosen = pressed || (isTable(learn) && learn.rows.length > 0) || data?.job?.steps?.export?.state === "done";
  stepPage(root, "export", data, ctx, {
    you: t("export.you"),
    // Claude's "Save these rules?" is answered by the ticks: no Yes / No of its own (Proceed sends the ticks, then yes)
    labels: { save: { no: null, text: t("export.save_ticked") } },
    // Proceed on Claude's learning question also sends each rule's tick: learn:<id> save / decline, with where to keep it
    gateExtra: () => ({ before: async () => {
      for (const { id, box, scope } of picks.get(key) || []) {
        await ctx.send({ type: "answer", step: "export", gate: null, target: `learn:${id}`,
          value: { decision: box.checked ? "save" : "decline", scope: scope.value } });
      }
    } }),
    body: () => [
      tempEnBanner(ctx, data),
      settingsCard(data),
      // "Done exporting?" goes once it's answered: a button pressed, rules proposed, or the video finished
      chosen ? null : h("section", { class: "card" }, h("h3", {}, t("export.done_h")),
        h("p", { class: "hint" }, t("export.done_p")),
        h("div", { class: "row", style: "margin-top:10px" },
          actionButton(ctx, data, "export", "export:learn", t("export.learn"), { primary: true }),
          // exported, but no learning step this time: Claude finishes the video without proposing rules
          actionButton(ctx, data, "export", "export:skip-learn", t("export.skip_learn")))),
      learnCard(ctx, data, learn),
    ].filter(Boolean),
  });
}
