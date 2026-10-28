// Dashboard: a card per video folder (each with its "what to do now" line), "Try a practice video", recent activity
// across videos, the setup check, "New video".
import { h, icon, chip, checksTable, relTime, stepTitle, STEPS, copyButton } from "../ui.js";
import { t } from "../words.js";
import { nowStrip } from "../nextstep.js";

const PRACTICE = "/practice-muna";  // what the editor types in Claude; the app cannot start Claude itself

const REFRESH_MS = 5000;
const MAX_JOBS = 12;  // videos whose job is read for cards and activity
const THUMB = {  // theme tokens only
  you: "linear-gradient(135deg, var(--panel2), var(--accent))",
  wait: "linear-gradient(135deg, var(--panel2), var(--wait))",
  ok: "linear-gradient(135deg, var(--panel2), var(--ok))",
  err: "linear-gradient(135deg, var(--panel2), var(--err))",
  mute: "linear-gradient(135deg, var(--panel2), var(--dim))",
};

const BAR = { you: "accent", wait: "wait", ok: "ok", err: "err", mute: "accent" };
const posix =(p) => String(p || "").replace(/\\/g, "/");
const jobLink = (folder, step) => `#/job/${encodeURIComponent(folder)}${step ? "/" + step : ""}`;

function greeting() {
  const hr = new Date().getHours();
  return t(hr < 12 ? "dash.morning" : hr < 18 ? "dash.afternoon" : "dash.evening");
}

/** [chip text, status] for a video from its job (or its summary while the job is loading). */
function videoStatus(summary, job) {
  if (job?.gate || summary.waiting) return [t("state.waiting"), "you"];
  const states = STEPS.map((s) => job?.steps?.[s]?.state);
  if (states.includes("error")) return [t("state.error"), "err"];
  if (states.includes("working")) return [t("state.working"), "wait"];
  if (summary.progress >= 1) return [t("state.done"), "ok"];
  if (!summary.progress) return [t("state.pending"), "mute"];
  return [t("dash.in_progress"), "mute"];
}

function card(summary, reply) {
  const job = reply?.job;
  const folder = posix(summary.path);
  const [text, status] = videoStatus(summary, job);
  const c = job?.card || {};
  const style = c.style || summary.style;
  const lang = c.language || summary.language;
  const temp = c.temp_en === "on" || String(c.temp_en || "").startsWith("partial:") ? t("dash.temp_on") : "";
  const n = Array.isArray(c.timelines) ? c.timelines.length : 0;
  const timelines = n ? t(n > 1 ? "dash.timelines" : "dash.timelines_one", { n }) : "";
  const client = c.client || summary.client;
  const meta = [client, style, lang ? lang + temp : "", timelines].filter(Boolean).join(" · ") || t("dash.meta_none");
  const step = job?.gate?.step || summary.step;
  const what = job?.gate?.title || stepTitle(step);
  const now = step ? t("dash.step_now", { n: STEPS.indexOf(step) + 1, what: `${what.charAt(0).toUpperCase()}${what.slice(1)}` })
    : t("dash.all_done");
  const pct = Math.round((summary.progress || 0) * 100);
  return h("a", { class: "proj", href: jobLink(folder, step), "aria-label": `${summary.name}: ${text}, ${now}` },
    h("div", { class: "thumb", style: `background:${THUMB[status]}` }, chip(text, status)),
    h("h3", {}, summary.name), h("div", { class: "meta" }, meta), h("div", { class: "now" }, now),
    reply ? nowStrip(reply, "card") : null,
    h("div", { class: "bar", role: "progressbar", "aria-valuenow": String(pct), "aria-valuemin": "0", "aria-valuemax": "100",
      "aria-label": t("dash.progress") }, h("i", { style: `width:${pct}%;background:var(--${BAR[status]})` })));
}

function practiceCard() {
  return h("section", { class: "card practice", "aria-labelledby": "practice-h" },
    h("h3", { id: "practice-h" }, t("practice.title")), h("p", { class: "hint" }, t("practice.what")),
    h("div", { class: "row" }, h("span", {}, t("practice.type")), h("code", { class: "mono cmd" }, PRACTICE),
      copyButton(PRACTICE, t("practice.copy"))));
}

const setupTable = (checks, older) => checksTable(checks, [[t("dash.older_check"), chip(String(older), "mute")]]);

export function render(root, data, ctx) {
  const sub = h("p", {}, t("dash.looking"));
  const grid = h("div", { class: "grid3" });
  const practice = h("div", {});
  const tryIt = practiceCard();
  const older = h("div", {});
  const activity = h("ul", { class: "act" }, h("li", {}, t("common.loading")));
  const setup = h("div", {}, h("p", { class: "hint" }, t("common.checking")));
  const newBtn = h("button", { class: "btn pri", type: "button", onclick: () => ctx.openDialog("new") }, icon("plus"), t("dash.new_video"));
  root.append(
    h("div", { class: "head" }, h("div", {}, h("h1", {}, greeting()), sub), newBtn),
    grid, tryIt, practice, older,
    h("div", { class: "grid2", style: "margin-top:20px" },
      h("section", { class: "card" }, h("h3", {}, t("dash.recent")), activity),
      h("section", { class: "card" }, h("h3", {}, t("checks.title")), setup)));

  const jobs = new Map();  // folder -> the /api/job reply (job, keyframes, storyboard, events, listening)
  const etags = new Map();  // folder -> {value}: If-None-Match per video, so an unchanged job costs a 304
  let summaries = [], checks = null, alive = true, busy = false;

  const draw = () => {
    const withJob = summaries.filter((s) => s.has_job && !s.practice);
    const practiceJobs = summaries.filter((s) => s.has_job && s.practice);
    const without = summaries.filter((s) => !s.has_job);
    const waiting = withJob.filter((s) => s.waiting).length;
    const active = withJob.filter((s) => (s.progress || 0) < 1).length;
    sub.textContent = t(active === 1 ? "dash.sub_one" : "dash.sub", { active, waiting });
    grid.replaceChildren(...(withJob.length ? withJob.map((s) => card(s, jobs.get(posix(s.path))))
      : [h("section", { class: "card" }, h("h3", {}, t("dash.none_h")), h("p", { class: "hint" }, t("dash.none_p")))]));
    practice.replaceChildren(...(practiceJobs.length ? [h("h2", { class: "section-h" }, t("dash.practice_h")),
      h("div", { class: "grid3" }, practiceJobs.map((s) => card(s, jobs.get(posix(s.path)))))] : []));
    older.replaceChildren(...(without.length ? [h("details", { class: "older" },
      h("summary", {}, t("dash.older", { n: without.length })),
      h("ul", {}, without.map((s) => h("li", { title: posix(s.path) }, s.name, s.practice ? t("dash.practice_tag") : ""))))] : []));

    const lines = [];
    for (const s of summaries) {
      const job = jobs.get(posix(s.path))?.job;
      for (const e of job?.log || []) lines.push({ ...e, video: s.name, folder: posix(s.path) });
    }
    lines.sort((a, b) => Date.parse(b.at) - Date.parse(a.at));
    activity.replaceChildren(...(lines.length ? lines.slice(0, 8).map((e) => h("li", {},
      h("time", { datetime: e.at, title: e.at }, relTime(e.at)),
      h("span", {}, e.text.replace(/^\s*\[[a-z]+\]\s*/, ""), " · ", h("a", { href: jobLink(e.folder) }, e.video))))
      : [h("li", {}, t("common.nothing_yet"))]));
    setup.replaceChildren(checks ? setupTable(checks, without.length) : h("p", { class: "hint" }, t("common.checking")));
  };

  const round = async () => {
    try {
      summaries = await ctx.api("/api/jobs") || [];
    } catch (e) {
      sub.textContent = e.message;
      return;
    }
    const read = summaries.filter((s) => s.has_job).slice(0, MAX_JOBS);
    await Promise.all(read.map(async (s) => {
      const folder = posix(s.path);
      if (!etags.has(folder)) etags.set(folder, { value: null });
      try {
        const reply = await ctx.api(`/api/job?folder=${encodeURIComponent(folder)}`, { etag: etags.get(folder) });
        if (reply) jobs.set(folder, reply);  // null = 304, the job we have is current
      } catch { /* the summary still shows the card */ }
    }));
    if (alive) draw();
  };
  const loadJobs = async () => {  // a tick is skipped while the last round still runs
    if (busy) return;
    busy = true;
    try { await round(); } finally { busy = false; }
  };
  const loadChecks = async () => {
    try { checks = await ctx.api("/api/checks"); } catch (e) { checks = [{ name: t("checks.title"), ok: false, detail: e.message }]; }
    if (alive) draw();
  };

  loadJobs();
  loadChecks();
  const timer = setInterval(loadJobs, REFRESH_MS);
  return () => { alive = false; clearInterval(timer); };
}
