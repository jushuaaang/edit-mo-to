// Dashboard: a card per video folder (each with its "what to do now" line), "Try a practice video" (Start practice:
// POST /api/practice opens the editor's own Claude in a visible window; the Copy fallback shows only when that can't
// happen), recent activity across videos, the setup check, "New video", and the plan usage box (usageCard).
import { h, icon, chip, checksTable, relTime, stepTitle, STEPS, copyButton } from "../ui.js";
import { t } from "../words.js";
import { nowStrip } from "../nextstep.js";

const PRACTICE = "/practice-muna";  // what Start practice runs, and what the editor types in Claude when it can't
const FALLBACK = new Set(["no-claude", "failed", "unsupported"]);  // these replies show the Copy fallback
const PRACTICE_WHY = { "no-claude": "practice.no_claude", failed: "practice.failed", unsupported: "practice.unsupported",
  busy: "practice.busy" };
let practiceReply = null;  // the last Start practice reply, kept when the page re-renders (a language change)

const REFRESH_MS = 5000;
const USAGE_MS = 60000;  // the usage box reads /api/usage again this often (and on "Update my usage")
const USAGE_CMD = "/usage";  // what the editor types in Claude for the exact number (the manual fallback)
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

/** "Try a practice video": Start practice asks the server to open Claude in a window the editor sees (the command is
 *  fixed in the server). Only when it can't (no `claude` command, the launch failed, or this system can't open a
 *  window) the card says why in plain words and shows "In Claude, type: /practice-muna [Copy]" instead. */
function practiceCard(ctx) {
  const status = h("p", { class: "hint", role: "status" });
  const fallback = h("div", { class: "row", hidden: true }, h("span", {}, t("practice.type")),
    h("code", { class: "mono cmd" }, PRACTICE), copyButton(PRACTICE, t("practice.copy")));
  const btn = h("button", { class: "btn pri", type: "button" }, t("practice.start"));
  const show = (reply) => {
    practiceReply = reply;
    status.textContent = !reply ? "" : reply.ok ? t("practice.opened")
      : [t(PRACTICE_WHY[reply.reason] || "practice.failed"),
        reply.hint === "automation" ? t("practice.mac_automation") : ""].filter(Boolean).join(" ");
    status.className = reply && !reply.ok && reply.reason !== "busy" ? "msg err" : "hint";
    fallback.hidden = !(reply && !reply.ok && FALLBACK.has(reply.reason));
  };
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    status.className = "hint";
    status.textContent = t("practice.starting");
    let reply;
    try {
      reply = await ctx.api("/api/practice", { body: {} });
    } catch {
      reply = { ok: false, reason: "failed" };
    }
    show(reply?.ok || PRACTICE_WHY[reply?.reason] ? reply : { ok: false, reason: "failed" });
    btn.disabled = false;
  });
  show(practiceReply);
  return h("section", { class: "card practice", "aria-labelledby": "practice-h" },
    h("h3", { id: "practice-h" }, t("practice.title")), h("p", { class: "hint" }, t("practice.what")),
    h("div", { class: "row" }, btn), status, fallback);
}

const pct = (n) => String(Math.round(n));
const clock = (iso) => { const d = new Date(iso); return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }); };
const resetWhen = (epoch) => new Date(epoch * 1000).toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" });

/** 1234567 -> "1.2 million", 45600 -> "46 thousand" (the token counts are always "about"). */
function tokenWords(n) {
  if (n >= 1e6) return t("usage.million", { n: (n / 1e6).toFixed(1) });
  if (n >= 1e3) return t("usage.thousand", { n: Math.round(n / 1e3) });
  return String(n);
}

/** Token Details: today, this week, the heaviest videos (from Claude Code's logs: numbers only). */
function usageDetails(tokens) {
  if (!tokens) return [h("p", {}, h("b", {}, t("usage.not_available"))), h("p", { class: "hint" }, t("usage.not_available_p"))];
  const jobs = (tokens.per_job || []).filter((j) => j && j.tokens > 0).slice(0, 5);
  const about = (n) => t("usage.tokens_about", { n: tokenWords(n) });
  return [
    h("dl", { class: "usage-kv" }, h("dt", {}, t("usage.today")), h("dd", {}, about(tokens.today?.total || 0)),
      h("dt", {}, t("usage.week_l")), h("dd", {}, about(tokens.week?.total || 0))),
    jobs.length ? h("table", {}, h("thead", {}, h("tr", {}, ["th_video", "th_tokens", "th_claude", "th_helpers", "th_pct"]
      .map((k) => h("th", {}, t(`usage.${k}`))))),
    h("tbody", {}, jobs.map((j) => h("tr", {}, h("td", {}, j.name, j.practice ? t("dash.practice_tag") : ""),
      h("td", {}, tokenWords(j.tokens)), h("td", {}, tokenWords(j.claude)), h("td", {}, tokenWords(j.helpers)),
      h("td", {}, j.pct === null || j.pct === undefined ? "–" : `${pct(j.pct)}%`))))) : null,
    jobs.some((j) => j.about) ? h("p", { class: "hint" }, t("usage.overlap_note")) : null,
  ].filter(Boolean);
}

/** The plan usage box (spec "Usage read automatically" and "Manual fallback"): the week and 5-hour % the project
 *  status line saved, % per video, videos left, token Details. "Update my usage" reads again now; it is highlighted
 *  with "old" while the reading is missing or over 30 minutes old (and no fresh typed reading stands in). Only then the
 *  box says what to do and offers the two-step manual box (type /usage, type the weekly %, Save). Every guess says
 *  "about"; nothing is shown that the server did not send. */
function usageCard(ctx) {
  const btn = h("button", { class: "btn sm", type: "button" }, t("usage.update"));
  const lines = h("div", { class: "usage-lines" });
  const status = h("p", { class: "hint", role: "status" });
  const field = h("input", { class: "f usage-pct", type: "number", min: "0", max: "100", step: "1", inputmode: "numeric",
    "data-key": "usage-pct", "aria-label": t("usage.pct_label") });
  const note = h("p", { class: "msg", role: "status" });
  const save = h("button", { class: "btn sm pri", type: "button" }, t("common.save"));
  const manualBox = h("div", { class: "usage-manual", hidden: true },
    h("p", { class: "usage-what" }, t("usage.open_claude")),
    h("p", { class: "hint" }, t("usage.manual_h")),
    h("div", { class: "row" }, h("span", {}, t("usage.step1")), h("code", { class: "mono cmd" }, USAGE_CMD), copyButton(USAGE_CMD)),
    h("div", { class: "row" }, h("label", {}, t("usage.step2"), field), save), note);
  const details = h("div", {});
  const card = h("section", { class: "card usage", "aria-labelledby": "usage-h" },
    h("div", { class: "row spread" }, h("h3", { id: "usage-h" }, t("usage.title")), btn),
    lines, manualBox, h("p", { class: "hint" }, t("usage.hint_exact")), status,
    h("details", { class: "usage-details" }, h("summary", {}, t("usage.details")), details));

  const show = (u) => {
    const auto = u?.auto, man = u?.manual;
    const fresh = auto && !u.stale;
    const out = [];
    if (fresh && auto.week_pct !== null) {
      out.push(h("p", { class: "usage-big" }, auto.week_resets_at
        ? t("usage.week", { pct: pct(auto.week_pct), when: resetWhen(auto.week_resets_at) })
        : t("usage.week_plain", { pct: pct(auto.week_pct) })));
    } else if (u?.source === "manual" && man?.last) {
      out.push(h("p", { class: "usage-big" }, t("usage.week_about",
        { pct: pct(Math.min(100, u.week_pct)), last: pct(man.last.pct), time: clock(man.last.at) })));
    }
    if (fresh && !auto.five_hour_old && auto.five_hour_pct !== null && auto.five_hour_pct !== undefined) {
      out.push(h("p", {}, t("usage.now", { pct: pct(auto.five_hour_pct) })));
    }
    const known = Boolean(u) && u.per_video_pct !== null && u.per_video_pct !== undefined;  // 0 is a real average
    out.push(h("p", {}, !known ? t("usage.not_enough", { n: Math.min(3, u?.videos_counted || 0) })
      : u.per_video_pct < 1 ? t("usage.per_video_small") : t("usage.per_video", { pct: pct(u.per_video_pct) })));
    if (u?.videos_left !== null && u?.videos_left !== undefined) {
      out.push(h("p", { class: "usage-left" }, u.videos_left === 1 ? t("usage.left_one") : t("usage.left", { n: u.videos_left })));
    }
    lines.replaceChildren(...out);
    const old = !u || (u.stale && (!man || man.old));
    btn.className = old ? "btn sm pri" : "btn sm";
    btn.textContent = old ? t("usage.update_old") : t("usage.update");
    manualBox.hidden = !(!u || u.stale);
    status.textContent = fresh && auto.week_at ? t("usage.read_at", { time: clock(auto.week_at) }) : "";
    details.replaceChildren(...usageDetails(u?.tokens));
  };

  let alive = true;
  const load = async () => {
    try {
      const u = await ctx.api("/api/usage");
      if (alive) show(u);
    } catch {
      if (alive) { show(null); status.textContent = t("usage.cant_read"); }
    }
  };
  btn.addEventListener("click", async () => { btn.disabled = true; await load(); btn.disabled = false; });
  save.addEventListener("click", async () => {
    const n = field.value.trim() === "" ? NaN : Number(field.value);
    if (!(n >= 0 && n <= 100)) { note.className = "msg err"; note.textContent = t("usage.bad_pct"); return; }
    save.disabled = true;
    try {
      show(await ctx.api("/api/usage", { body: { pct: n } }));
      field.value = "";
      note.className = "msg ok";
      note.textContent = t("usage.saved");
    } catch (e) {
      note.className = "msg err";
      note.textContent = e.message || t("usage.cant_read");
    }
    save.disabled = false;
  });
  load();
  const timer = setInterval(load, USAGE_MS);
  return { card, stop: () => { alive = false; clearInterval(timer); } };
}

const setupTable = (checks, older) => checksTable(checks, [[t("dash.older_check"), chip(String(older), "mute")]]);

export function render(root, data, ctx) {
  const sub = h("p", {}, t("dash.looking"));
  const grid = h("div", { class: "grid3" });
  const practice = h("div", {});
  const tryIt = practiceCard(ctx);
  const plan = usageCard(ctx);
  const older = h("div", {});
  const activity = h("ul", { class: "act" }, h("li", {}, t("common.loading")));
  const setup = h("div", {}, h("p", { class: "hint" }, t("common.checking")));
  const newBtn = h("button", { class: "btn pri", type: "button", onclick: () => ctx.openDialog("new") }, icon("plus"), t("dash.new_video"));
  root.append(
    h("div", { class: "head" }, h("div", {}, h("h1", {}, greeting()), sub), newBtn),
    grid, plan.card, tryIt, practice, older,
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
  return () => { alive = false; clearInterval(timer); plan.stop(); };
}
