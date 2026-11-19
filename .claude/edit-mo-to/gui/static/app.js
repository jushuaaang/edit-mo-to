// Edit Mo To app shell: API calls, hash router, polling, the three-column layout.
//
// Routes:  #/  dashboard   ·   #/settings   ·   #/job/<encoded folder>/<step>
// Pages:   pages/<name>.js exports render(root, data, ctx); it may return a cleanup function.
//          data = the /api/job reply for the open video (or null), ctx = see ui.js header.
//          A page whose module is not there yet shows "This page is coming".
// Words:   every word comes from words.js (t). index.html's fixed words carry data-w / data-w-label / data-w-ph keys
//          (applyStaticWords). When the language changes (Settings, or Claude's `job.py lang` seen on the prefs refresh
//          every CURRENT_MS) the shell and the open page re-render at once, keeping what the editor typed.

import { h, icon, stepChip, STEPS, stepTitle, relTime, gateBar, reopenGate, dialog, toast, previousStep, helpTip, copyButton } from "./ui.js";
import { watchQuestion, titled, loadPrefs, onLangChange } from "./nextstep.js";
import { t, getLang, wordsIn } from "./words.js";

const POLL_MS = 1500;
const CURRENT_MS = 5000;  // /api/current and this computer's prefs (the language) are read again this often

// ---------- API ----------

let token = null;  // fallback when the cookie is missing: ?k=<token> on this page's URL
try {
  const k = new URLSearchParams(location.search).get("k");
  if (k) {
    sessionStorage.setItem("emt-k", k);
    history.replaceState(null, "", location.pathname + location.hash);
  }
  token = sessionStorage.getItem("emt-k");
} catch { /* storage blocked: the cookie still works */ }

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

async function request(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (token) headers["X-EMT-Token"] = token;
  let body = opts.body;
  if (body !== undefined && !(body instanceof Blob) && typeof body !== "string") {
    body = JSON.stringify(body);
    headers["Content-Type"] = "application/json";
  }
  let res;
  try {
    res = await fetch(path, { method: opts.method || (body !== undefined ? "POST" : "GET"), headers, body,
      credentials: "same-origin", cache: "no-store" });
  } catch {
    setConn(false);
    throw new ApiError(0, t("app.no_server"));
  }
  setConn(true);
  if (res.status === 401) showKeyProblem();
  return res;
}

/** JSON API call. opts: {method, body (object -> JSON), headers, etag}. Resolves to the reply (null on 304).
 *  etag: a {value} box kept by the caller; sent as If-None-Match and updated from the reply's ETag. */
export async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (opts.etag?.value) headers["If-None-Match"] = opts.etag.value;
  const res = await request(path, { ...opts, headers });
  if (res.status === 304) return null;
  if (opts.etag && res.ok) opts.etag.value = res.headers.get("ETag");
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = null; }
  if (!res.ok) throw new ApiError(res.status, data?.error || t("app.server_said", { status: res.status }));
  return data;
}

/** PUT /api/upload with progress. query: {folder, kind, name, id?}. Check type and size first (ui.uploadProblem). */
export function upload(query, file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", "/api/upload?" + new URLSearchParams(query).toString());
    if (token) xhr.setRequestHeader("X-EMT-Token", token);
    xhr.upload.onprogress = (e) => { if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total); };
    xhr.onload = () => {
      let data = null;
      try { data = JSON.parse(xhr.responseText); } catch { data = null; }
      if (xhr.status >= 200 && xhr.status < 300) { kick(); resolve(data); } else {
        reject(new ApiError(xhr.status, data?.error || t("app.upload_refused", { status: xhr.status })));
      }
    };
    xhr.onerror = () => reject(new ApiError(0, t("app.upload_stopped")));
    xhr.send(file);
  });
}

// ---------- state ----------

const state = {
  route: { page: "dashboard" }, current: null, folder: null,
  data: null, jobError: null, etag: null, connected: null,
};
const $ = (sel) => document.querySelector(sel);
let pollSeq = 0, pollTimer = null, inflight = 0, kicked = false, loopNow = null;
let renderSeq = 0, cleanup = null;
const modules = new Map();

export function jobHash(folder, step) {
  return `#/job/${encodeURIComponent(folder)}${step ? "/" + step : ""}`;
}

function parseRoute() {
  const parts = (location.hash || "#/").replace(/^#\/?/, "").split("/");
  if (parts[0] === "settings") return { page: "settings" };
  if (parts[0] === "job" && parts[1]) {
    try {
      return { page: "job", folder: decodeURIComponent(parts[1]), step: STEPS.includes(parts[2]) ? parts[2] : null };
    } catch { /* bad escape: fall back to the dashboard */ }
  }
  return { page: "dashboard" };
}

// ---------- polling ----------

/** Poll /api/job for folder every 1500 ms with If-None-Match; re-render on change. */
export function poll(folder) {
  const my = ++pollSeq;
  clearTimeout(pollTimer);
  state.etag = null;
  kicked = false;
  loopNow = null;
  if (!folder) return;
  const loop = async () => {
    if (my !== pollSeq || inflight === my) return;
    inflight = my;
    try { await pollOnce(folder, my); } finally { if (inflight === my) inflight = 0; }
    if (my !== pollSeq) return;
    clearTimeout(pollTimer);
    pollTimer = setTimeout(loop, kicked ? 0 : POLL_MS);
    kicked = false;
  };
  loopNow = loop;
  loop();
}

/** Poll again now (after the editor sent something). */
function kick() {
  if (!loopNow) return;
  if (inflight) { kicked = true; return; }
  clearTimeout(pollTimer);
  loopNow();
}

async function pollOnce(folder, my) {
  let res;
  try {
    res = await request(`/api/job?folder=${encodeURIComponent(folder)}`,
      { headers: state.etag ? { "If-None-Match": state.etag } : {} });
  } catch { return; }
  if (my !== pollSeq || res.status === 304) return;
  const data = await res.json().catch(() => null);
  if (res.ok) {
    state.etag = res.headers.get("ETag");
    state.data = data;
    state.jobError = null;
    autoFollow(folder, data);
    watchQuestion(folder, data);  // pop-up, sound and "(1)" in the tab title when a new question opens
  } else {
    state.etag = null;
    state.data = null;
    state.jobError = { status: res.status, message: data?.error || "" };
    if (res.status === 404) followRename(folder);
  }
  changed();
}

/** Claude moved on: when the step it asks about, works on or waits on changes, open that step's page. Only on a
 *  change, so the editor can still look at other steps; the first look at a video only notes where Claude is. */
const followed = new Map();  // folder -> "<step>|<gate id or working>" last seen
function autoFollow(folder, data) {
  const job = data?.job;
  // where Claude is: the step it asks about, else one it works on, else one waiting on the editor without a question
  // (e.g. Export: "export, then press I exported")
  const busy = (st) => STEPS.find((s) => job?.steps?.[s]?.state === st);
  const finished = job?.steps?.export?.state === "done";
  const step = finished ? null : job?.gate?.step || busy("working") || busy("waiting") || null;
  const key = finished ? "finished" : step ? `${step}|${job.gate?.id || job.steps[step].state}` : "";
  const prev = followed.get(folder);
  followed.set(folder, key);
  // the whole workflow just finished: back to the Dashboard (only at that moment; a finished video can still be opened)
  if (finished && prev !== undefined && prev !== "finished") {
    toast(t("app.video_finished"), 4000);
    if (state.route.page === "job" && state.folder === folder) location.hash = "#/";
    return;
  }
  if (prev === undefined || !step || key === prev || prev.startsWith(`${step}|`)) return;
  if (state.route.page === "job" && state.folder === folder && state.route.step !== step) {
    location.hash = `#/job/${encodeURIComponent(folder)}/${step}`;
  }
}

/** Claude renamed this video's folder (step 2 names it after the client and product): the new folder is the current
 *  job and its job.json says `renamed_from` = this folder, so go there on the same page instead of "can't open". */
async function followRename(folder) {
  try {
    const cur = (await api("/api/current"))?.folder;
    if (!cur || cur === folder || state.folder !== folder) return;
    const res = await request(`/api/job?folder=${encodeURIComponent(cur)}`);
    const data = res.ok ? await res.json() : null;
    if (data?.job?.renamed_from !== folder || state.folder !== folder) return;
    const page = state.route.page === "job" ? location.hash.split("/").slice(3).join("/") : "";
    location.hash = `#/job/${encodeURIComponent(cur)}${page ? "/" + page : ""}`;
  } catch { /* the error card stays */ }
}

async function refreshCurrent() {
  loadPrefs(api);  // the language may have changed (Settings in another tab, or Claude's `job.py lang`)
  try {
    const cur = (await api("/api/current"))?.folder || null;
    if (cur !== state.current) {
      state.current = cur;
      if (state.route.page !== "job") setFolder(cur);
    }
  } catch { /* connection line shows it */ }
}

function setFolder(folder) {
  if (folder === state.folder) return;
  state.folder = folder;
  state.data = null;
  state.jobError = null;
  renderShell();
  poll(folder);
}

// ---------- context for pages ----------

async function sendEvent(folder, event) {
  if (!folder) throw new ApiError(0, t("app.open_first"));
  const ev = await api("/api/inbox", { body: { folder, event } });
  if (event?.type !== "message" && !event?.early) { state.sentAt = Date.now(); state.changing = null; }  // card at once
  renderWorking();
  kick();
  return ev;
}

async function openDialog(name, args) {
  let mod = null;
  try { mod = await import("./dialogs.js"); } catch { mod = null; }
  if (mod?.open) return mod.open(name, args, makeCtx(state.folder));
  const text = t(name === "new" ? "app.dialog_new_coming" : "app.dialog_coming");
  return dialog(name, h("p", {}, text), [{ label: t("common.close"), primary: true }],
    { title: name === "new" ? t("dash.new_video") : name });
}

function makeCtx(folder) {
  return {
    folder,
    send: (event) => sendEvent(folder, event),
    saveGui: async (patch) => { const r = await api("/api/gui", { body: { folder, patch } }); kick(); return r; },
    openDialog,
    api,
    upload,
    get data() { return state.data; },
    go: (hash) => { location.hash = hash; },
  };
}

// ---------- shell: sidebar, rail, connection ----------

function setConn(ok) {
  if (state.connected === ok) return;
  state.connected = ok;
  drawConn();
}

function drawConn() {
  if (state.connected === null) return;
  const ok = state.connected;
  $("#conn").replaceChildren(h("span", { class: `dot ${ok ? "ok" : "err"}` }),
    ok ? t("app.connected", { host: location.host }) : t("app.not_connected"));
}

/** index.html's fixed words in the current language (branding and the verse carry no key and never change). */
function applyStaticWords() {
  document.documentElement.lang = getLang() === "tl" ? "fil" : "en";
  document.querySelectorAll("[data-w]").forEach((el) => { el.textContent = t(el.dataset.w); });
  document.querySelectorAll("[data-w-label]").forEach((el) => el.setAttribute("aria-label", t(el.dataset.wLabel)));
  document.querySelectorAll("[data-w-ph]").forEach((el) => el.setAttribute("placeholder", t(el.dataset.wPh)));
}

function showKeyProblem() {
  if ($("#key-problem")) return;
  $("#view").prepend(h("div", { class: "banner err", id: "key-problem", role: "alert" },
    h("b", {}, t("app.key_h")), h("span", {}, t("app.key_p"))));
}

function activeStep(job) {
  const steps = job?.steps || {};
  if (job?.gate?.step) return job.gate.step;
  const by = (states) => STEPS.find((s) => states.includes(steps[s]?.state));
  return by(["waiting", "working", "error"]) || by(["pending"]) || "brief";
}

function stepLink(step, i, job, route) {
  const st = job.steps?.[step]?.state || "pending";
  const optional = step === "storyboard" && st === "pending";
  const open = st === "pending" && Boolean(state.data?.early?.[step]);  // takes early input (spec "Working ahead")
  const prev = st === "pending" && !open ? previousStep(step, job) : null;
  const cls = optional ? "optional" : st;
  const n = st === "done" ? icon("check") : st === "error" ? "!" : String(i + 1);
  const tag = st === "waiting" ? ["tag.you", "you"] : st === "working" ? ["tag.working", "wait"] : st === "error" ? ["tag.error", "err"]
    : st === "skipped" ? ["tag.skipped", "mute"] : optional ? ["tag.optional", "opt"] : open ? ["tag.open", "open"] : null;
  const current = route.page === "job" && route.step === step;
  return h("a", { href: jobHash(state.folder, step), class: cls, "aria-current": current ? "page" : null },
    h("span", { class: "n", "aria-hidden": "true" }, n),
    h("span", { class: "label" }, stepTitle(step), prev ? h("small", { class: "sub" }, t("app.waits_for", { step: stepTitle(prev) })) : null),
    st === "done" ? h("span", { class: "sr" }, t("app.sr_done")) : null,
    tag ? h("span", { class: `tag ${tag[1]}` }, t(tag[0])) : null);
}

const CARD_HELP = { temp_en: "temp_en", vo: "vo", timelines: "timeline", generator: "model" };  // ⓘ after these
const CARD_ORDER = ["client", "product", "style", "language", "temp_en", "folder", "vo", "generator", "timelines",
  "broll_source", "clips_folder", "project"];  // labels: WORDS.card.<key>; other keys Claude adds show under their own name
const PATH_KEYS = new Set(["folder", "clips_folder"]);
const ONLY_WHEN_SET = new Set(["broll_source", "clips_folder"]);  // rows most videos never fill: no "Not yet" row  // shown as the folder's name; the full path on hover and Copy
const SOURCE_WORDS = { client: "prompts.src_client", ai: "prompts.src_ai", both: "prompts.src_both" };
const baseName = (p) => String(p ?? "").replace(/[\\/]+$/, "").split(/[\\/]/).pop();

/** A path row of the job card: the last folder name (short, no 6-line wrap), the full path as its title and a Copy. */
function pathValue(full) {
  return h("dd", { class: "pathval" }, h("span", { class: "mono", title: full }, baseName(full) || full),
    copyButton(full, t("common.copy")));
}

function tempEn(value) {
  if (!value) return null;
  if (value === "on") return [t("card.temp_on"), "warn"];
  if (value.startsWith("partial:")) return [t("card.temp_partial", { names: value.slice(8) }), "warn"];
  if (value === "removed") return [t("card.temp_removed"), ""];
  if (value === "off") return [t("card.temp_off"), ""];
  return [value, ""];
}

// ---------- "Claude is working" card ----------

const WORK_TYPES = new Set(["answer", "action", "edit", "approve", "message", "upload"]);
const WORK_FRESH_MS = 15 * 60 * 1000;  // an unhandled send older than this no longer counts as "Claude got it"
const SENT_SHOW_MS = 8000;  // after Proceed / Submit the card shows at once, until Claude's own state takes over

/** What Claude is doing now, or null: a step that is `working` (its note, else its latest activity line), or something
 *  the editor just sent that Claude has not handled yet (at once after Proceed or Submit). An open question with nothing
 *  sent is the editor's turn: no card. */
function workingNow(data) {
  const job = data?.job;
  if (!job) return null;
  const step = job.gate || data.claude_window === "closed" ? null : STEPS.find((s) => job.steps?.[s]?.state === "working");
  if (step) {
    const mine = (job.log || []).filter((e) => String(e.text || "").startsWith(`[${step}]`));
    const plain = (e) => wordsIn(String(e.text).replace(/^\s*\[[a-z]+\]\s*/, ""), data);
    const note = job.steps[step].note ? wordsIn(job.steps[step].note, data) : (mine.length ? plain(mine[mine.length - 1]) : "");
    // what it just did on this step: the last few activity lines, newest first (the note itself not repeated)
    const done = mine.slice(-4).reverse().map((e) => ({ at: e.at, text: plain(e) })).filter((e) => e.text !== note).slice(0, 3);
    const todo = (job.steps[step].todo || []).filter((x) => x && x.text).map((x) => ({ text: wordsIn(String(x.text), data), done: Boolean(x.done) }));
    return { step, text: note || t("work.busy"), done, todo, left: timeLeft(job.steps[step], data.work_times?.[step]) };
  }
  const handled = new Set(job.handled || []);
  if (data.claude_window === "closed") return null;  // Claude's window is gone: nobody will pick it up (Resume shows)
  if (job.gate && state.changing === `${state.folder}|${job.gate.id}`) return null;  // the editor is changing them
  // the open question's answers so far; until every part has one (e.g. only the Quit CapCut banner's button was
  // pressed) it is still the editor's turn: no card over the page, the rest still to answer
  const mine = job.gate ? (data.events || []).filter((e) => e.type === "answer" && e.gate === job.gate.id && !e.stale) : [];
  const got = new Set(mine.map((e) => e.target));
  if (job.gate && !(job.gate.questions || []).every((q) => got.has(q.id))) return null;
  // sends Claude hasn't marked handled: the answers to the question still open (Claude hasn't moved on to a new one),
  // or anything sent while no question is open. Whether its listener is up doesn't matter: it restarts it at once.
  const fresh = (data.events || []).some((e) => WORK_TYPES.has(e.type) && !e.early && !e.stale && !handled.has(e.seq)
    && Date.now() - Date.parse(e.at) < WORK_FRESH_MS && (job.gate ? e.gate === job.gate.id : true));
  const justSent = Date.now() - (state.sentAt || 0) < SENT_SHOW_MS;
  // the open question's answers not picked up yet: they can still change (Change my answer on the card)
  const canChange = mine.length > 0 && mine.some((e) => !handled.has(e.seq));
  return fresh || justSent ? { step: null, text: t("work.got_it"), canChange } : null;
}

function renderWorking() {
  let card = $("#working");
  if (!card) {
    card = h("div", { class: "working", id: "working", role: "status", "aria-live": "polite", hidden: true });
    document.body.append(card);
  }
  const now = state.folder ? workingNow(state.data) : null;
  card.hidden = !now;
  // while Claude works: the page and the left sidebar dim and take no clicks or keys; the right panel stays usable
  document.body.classList.toggle("is-working", Boolean(now));
  for (const el of [$("#view"), document.querySelector(".side")]) {
    if (el) el.inert = Boolean(now);
  }
  if (!now) return;
  const n = now.step ? STEPS.indexOf(now.step) + 1 : 0;
  card.replaceChildren(h("span", { class: "spin", "aria-hidden": "true" }),
    h("div", { class: "working-body" },
      h("b", {}, t("work.title")),
      now.step ? h("div", { class: "working-step" }, t("work.step", { n, total: STEPS.length, step: stepTitle(now.step) })) : null,
      h("div", { class: "working-text" }, now.text),
      now.left && leftText(now.left) ? h("div", { class: "working-left" }, icon("clock"), leftText(now.left)) : null,
      now.todo?.length ? todoList(now.todo) : null,
      !now.todo?.length && now.done?.length ? h("ul", { class: "working-done" }, now.done.map((e) =>
        h("li", {}, h("span", { class: "tick", "aria-hidden": "true" }, "✓"), h("span", {}, e.text),
          h("time", { datetime: e.at }, relTime(e.at))))) : null,
      now.canChange ? h("button", { class: "linkish working-change", type: "button", onclick: () => {
        const gate = state.data?.job?.gate;
        if (!gate) return;
        reopenGate(state.folder, gate.id);
        state.changing = `${state.folder}|${gate.id}`;
        state.sentAt = 0;
        renderWorking();
        renderPage();
      } }, t("gate.change")) : null));
}

/** How long this stretch of work still takes, best guess first: the pace of Claude's ticked checklist items, then
 *  Claude's own `--eta`, then the usual time for this step on this computer. {secs left (may be < 0), elapsed} or null. */
function timeLeft(step, usual) {
  const at = (iso) => Date.parse(iso || "");
  const now = Date.now();
  const since = at(step.since);
  const elapsed = Number.isFinite(since) ? (now - since) / 1000 : null;
  const todo = step.todo || [];
  const ticks = todo.filter((x) => x.done && Number.isFinite(at(x.at))).map((x) => at(x.at)).sort((a, b) => a - b);
  const start = at(step.todo_at);
  if (ticks.length && Number.isFinite(start) && todo.length > ticks.length) {
    const per = (ticks[ticks.length - 1] - start) / ticks.length / 1000;  // seconds per item so far
    return { secs: per * (todo.length - ticks.length) - (now - ticks[ticks.length - 1]) / 1000, elapsed };
  }
  if (step.eta && Number.isFinite(at(step.eta.at))) return { secs: (at(step.eta.at) - now) / 1000 + step.eta.s, elapsed };
  if (usual && elapsed !== null) return { secs: usual - elapsed, elapsed };
  return elapsed !== null ? { secs: null, elapsed } : null;
}

/** "About 3 min left" / "Less than a minute left" / "Taking a bit longer than usual", with the time so far. */
function leftText(left) {
  const mins = (s) => Math.max(1, Math.round(s / 60));
  const so_far = left.elapsed !== null && left.elapsed >= 60 ? t("work.so_far", { n: mins(left.elapsed) }) : "";
  const est = left.secs === null ? "" : left.secs > 90 ? t("work.left_min", { n: mins(left.secs) })
    : left.secs > 0 ? t("work.left_soon") : t("work.left_over");
  return [est, so_far].filter(Boolean).join(" · ");
}

/** Claude's checklist for this step (`job.py step … --todo`): ticked boxes for what's done, the first open one is
 *  what it's on now. */
function todoList(items) {
  const now = items.findIndex((x) => !x.done);
  const left = items.filter((x) => !x.done).length;
  return h("div", { class: "todo" },
    h("div", { class: "todo-h" }, t("work.todo_h"), h("span", {}, t("work.todo_count", { done: items.length - left, total: items.length }))),
    h("ul", { role: "list" }, items.map((x, i) => h("li", { class: x.done ? "done" : i === now ? "now" : "" },
      h("span", { class: "box", "aria-hidden": "true" }, x.done ? icon("check") : null),
      h("span", { class: "sr" }, x.done ? t("work.todo_done") : i === now ? t("work.todo_now") : ""),
      h("span", {}, x.text)))));
}

let showEmptyCard = false;  // the job card's "Not yet" fields, hidden until asked for

/** The job card folds up (a one-line summary when closed); its open/closed state is remembered on this computer. */
function initJobCard() {
  const wrap = $("#jobcard-wrap");
  if (!wrap || wrap.dataset.ready) return;
  wrap.dataset.ready = "1";
  try { wrap.open = localStorage.getItem("emt.jobcard.open") === "1"; } catch { wrap.open = false; }
  wrap.addEventListener("toggle", () => { try { localStorage.setItem("emt.jobcard.open", wrap.open ? "1" : "0"); } catch { /* fine */ } });
}

function renderRail() {
  initJobCard();
  renderWorking();
  const job = state.data?.job;
  const card = job?.card || {};
  const dl = $("#jobcard");
  if (!job) {
    dl.replaceChildren(h("dt", {}, t("card.job")), h("dd", { class: "none" }, t(state.folder ? "common.loading" : "shell.no_video")));
  } else {
    const all = [...CARD_ORDER.filter((k) => !ONLY_WHEN_SET.has(k) || card[k]).map((k) => [k, t(`card.${k}`)]),
      ...Object.keys(card).filter((k) => !CARD_ORDER.includes(k)).map((k) => [k, k])];
    // filled fields only; the empty ones ("Not yet") behind "Show empty fields"
    const filled = ([k]) => Boolean(Array.isArray(card[k]) ? card[k].length : card[k]);
    const keys = showEmptyCard ? all : all.filter(filled);
    const hidden = all.length - all.filter(filled).length;
    const toggle = hidden ? h("dd", { class: "jc-more" }, h("button", { class: "linkish", type: "button",
      onclick: () => { showEmptyCard = !showEmptyCard; renderRail(); } },
    t(showEmptyCard ? "card.hide_empty" : "card.show_empty", { n: hidden }))) : null;
    dl.replaceChildren(...keys.flatMap(([k, label]) => {
      let v = card[k];
      if (Array.isArray(v)) v = v.join(", ");
      if (k === "temp_en") {
        const te = tempEn(v);
        return [h("dt", {}, label, helpTip("temp_en")), te ? h("dd", { class: te[1] || null }, te[0]) : h("dd", { class: "none" }, t("card.not_set"))];
      }
      const dt = h("dt", {}, label, CARD_HELP[k] ? helpTip(CARD_HELP[k]) : null);
      if (!v) return [dt, h("dd", { class: "none" }, t("card.not_yet"))];
      if (PATH_KEYS.has(k)) return [dt, pathValue(String(v))];
      if (k === "broll_source" && SOURCE_WORDS[String(v).toLowerCase()]) return [dt, h("dd", {}, t(SOURCE_WORDS[String(v).toLowerCase()]))];
      return [dt, h("dd", {}, String(v))];
    }), ...(toggle ? [h("dt", {}), toggle] : []));
  }
  $("#jobcard-sum").textContent = job ? [card.product || card.client, card.style].filter(Boolean).join(" · ") : "";
  // Claude's activity lines and Claude's own replies (job.py say: word for word, as in the chat), newest first
  // and the editor's own messages from the box below (a "You" bubble, "Claude is reading…" until Claude marks it read)
  const handledSeqs = new Set(job?.handled || []);
  const mine = (state.data?.events || []).filter((e) => e.type === "message").slice(-10).map((e) => ({ ...e, you: true }));
  const log = [...(job?.log || []).slice(-20), ...(job?.messages || []).slice(-20).map((e) => ({ ...e, say: true })), ...mine]
    .sort((a, b) => String(b.at).localeCompare(String(a.at)));
  $("#activity").replaceChildren(...(log.length ? log.map((e) => {
    if (e.you) {
      const read = handledSeqs.has(e.seq);
      return h("li", { class: "you" }, h("time", { datetime: e.at, title: e.at }, `${t("tag.you")} · ${relTime(e.at)}`),
        h("div", { class: "say-text" }, String(e.text || "")),
        read ? h("span", { class: "you-read" }, t("app.msg_read"))
          : h("span", { class: "you-wait", role: "status" }, h("span", { class: "spin sm", "aria-hidden": "true" }),
            t(state.data?.listening || state.data?.claude_window === "open" ? "app.msg_reading" : "app.msg_waiting")));
    }
    if (e.say) {
      return h("li", { class: "say" }, h("time", { datetime: e.at, title: e.at }, relTime(e.at)),
        h("div", { class: "say-text" }, String(e.text || "")));
    }
    const m = /^\s*\[([a-z]+)\]\s*/.exec(e.text || "");
    const text = wordsIn(m ? `${stepTitle(m[1])} · ${e.text.slice(m[0].length)}` : e.text, state.data);  // codes in words, display only
    return h("li", {}, h("time", { datetime: e.at, title: e.at }, relTime(e.at)), h("span", {}, text));
  }) : [h("li", {}, t(job ? "common.nothing_yet" : "app.open_to_see"))]));

  const lis = state.data?.listening;
  $("#listening").className = `status${lis ? " on" : ""}`;
  $("#listening").replaceChildren(...[h("span", { class: `pulse${lis ? "" : " off"}`, "aria-hidden": "true" }),
    h("span", {}, !state.folder ? t("app.no_video_talk")
      : lis ? t("app.listening", { step: stepTitle(lis.step) || t("app.this_job") }) : t("app.listening_off_short")),
    state.folder && !lis ? helpTip("listening") : null].filter(Boolean));  // the long "what happens to my message" behind ⓘ
  $("#job-send").disabled = !state.folder || !job;
  renderResume(job, lis);
}

// ---------- Resume with Claude ----------

const RESUME_IDLE_MS = 3 * 60 * 1000;  // no terminal to look at: no change for this long and nobody listening
const RESUME_WHY = { "no-claude": "practice.no_claude", failed: "practice.failed", unsupported: "practice.unsupported",
  busy: "practice.busy", listening: "resume.listening" };
let resumeNote = null;  // {text, cls, typed} of the last Resume click, kept across refreshes

/** Shown when a started video is unfinished, nobody is listening, and Claude's terminal is gone: the window the app
 *  opened is closed or Claude exited in it (`claude_window` "closed"). Never while that window still runs Claude
 *  ("open"). When the app opened no window (Claude started by hand, or macOS), it can't see the terminal: then only
 *  when a question waits unread or nothing has changed for a while. It opens a fresh Claude on this video (the same
 *  fixed command as Submit); the skill picks the video up where it stopped. */
function needsResume(job, lis, win) {
  if (!job || lis || win === "open" || job.steps?.export?.state === "done") return false;
  const started = job.gate || STEPS.some((s) => (job.steps?.[s]?.state || "pending") !== "pending");
  if (!started || Date.now() - (state.sentAt || 0) < 15000) return false;
  if (win === "closed") return true;
  return Boolean(job.gate) || Date.now() - Date.parse(job.updated || 0) > RESUME_IDLE_MS;
}

function renderResume(job, lis) {
  let box = $("#resume");
  if (!box) {
    box = h("div", { id: "resume", class: "resume", hidden: true });
    $("#listening").after(box);
  }
  const show = state.folder && needsResume(job, lis, state.data?.claude_window);
  box.hidden = !show && !resumeNote;
  if (box.hidden) return;
  const command = /[\\/]_practice[\\/]/.test(state.folder || "") ? "practice-muna" : "edit-mo-to";
  const btn = h("button", { class: "btn pri", type: "button", onclick: () => askResume(command) }, t("resume.button"));
  const note = resumeNote ? h("div", { class: resumeNote.cls, role: "status" }, resumeNote.text) : null;
  const typed = resumeNote?.typed ? h("div", { class: "row" }, h("span", {}, t("practice.type")),
    h("code", { class: "mono cmd" }, resumeNote.typed), copyButton(resumeNote.typed, t("practice.copy"))) : null;
  box.replaceChildren(...[show ? h("p", { class: "hint" }, t("resume.why")) : null, show ? btn : null, note, typed].filter(Boolean));
}

function askResume(command) {
  dialog("resume", h("p", {}, t("resume.confirm_p")), [
    { label: t("common.cancel") },
    { label: t("resume.go"), primary: true, onClick: () => resume(command, false) },
  ], { title: t("resume.title") });
}

/** POST /api/practice for this video. The server never opens a second Claude by itself: one already listening on the
 *  video ("listening"), or one that opened the app and waits (`attached`: the video goes to it); a video Claude changed
 *  in the last minutes ("recent") asks again before a new window (force). */
async function resume(command, force) {
  const folder = state.folder;
  let reply;
  try {
    reply = await api("/api/practice", { body: { command, folder, ...(force ? { force: true } : {}) } });
  } catch {
    reply = { ok: false, reason: "failed" };
  }
  if (reply?.reason === "recent") {
    dialog("resume-recent", h("p", {}, t("resume.recent_p", { n: Math.max(1, Math.round(reply.minutes || 0)) })), [
      { label: t("common.cancel") },
      { label: t("resume.anyway"), onClick: () => resume(command, true) },
    ], { title: t("resume.recent_title") });
    return;
  }
  if (!reply?.ok && !RESUME_WHY[reply?.reason]) reply = { ok: false, reason: "failed" };
  const soft = reply.reason === "busy" || reply.reason === "listening";
  resumeNote = reply.ok ? { cls: "msg ok", text: t(reply.attached ? "practice.attached" : "practice.opened") }
    : { cls: soft ? "msg ok" : "msg err", text: t(RESUME_WHY[reply.reason]), typed: soft ? null : `/${command}-app` };
  if (reply.ok) state.sentAt = Date.now();  // the working card shows while Claude picks it up
  renderRail();
}

function renderShell() {
  const route = state.route;
  document.querySelectorAll(".nav a[data-route]").forEach((a) => {
    if (a.dataset.route === route.page) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
  const job = state.data?.job;
  const name = state.folder ? state.folder.split("/").filter(Boolean).pop() : "";
  $("#job-name").textContent = name || t("shell.no_video");
  $("#job-name").title = state.folder || "";
  const steps = $("#steps");
  // the video's steps only while a video is open; the Dashboard and Settings show none
  const onVideo = route.page === "job";
  steps.hidden = !onVideo;
  $("#job-name").hidden = !onVideo;
  if (!onVideo) steps.replaceChildren();
  else if (!job) {
    const msg = !state.folder ? t("app.open_on_dash")
      : state.jobError ? jobErrorText(state.jobError) : t("common.loading");
    steps.replaceChildren(h("p", { class: "empty" }, msg));
  } else {
    steps.replaceChildren(...STEPS.map((s, i) => stepLink(s, i, job, route)));
  }
  renderRail();
}

function jobErrorText(err) {
  if (err.status === 404) return t("app.err_404");
  if (err.status === 403) return t("app.err_403");
  return err.message || t("app.err_load");
}

// ---------- pages ----------

function loadModule(name) {
  if (!modules.has(name)) modules.set(name, import(`./pages/${name}.js`).catch(() => null));
  return modules.get(name);
}

/** Re-render keeping what the editor typed in [data-key] fields, the focus and the scroll position. */
function keepInputs(root, fn) {
  const typed = new Map();
  root.querySelectorAll("[data-key]").forEach((el) => {
    if (el.type === "checkbox" || el.type === "radio") {
      if (el.checked !== el.defaultChecked) typed.set(el.dataset.key, { checked: el.checked });
    } else if ("value" in el && el.value !== el.defaultValue) typed.set(el.dataset.key, { value: el.value });
  });
  const active = document.activeElement;
  const focusKey = active && root.contains(active) ? active.dataset.key : null;
  const sel = focusKey && "selectionStart" in active ? [active.selectionStart, active.selectionEnd] : null;
  const main = $("#page"), top = main.scrollTop;
  fn();
  root.querySelectorAll("[data-key]").forEach((el) => {
    const was = typed.get(el.dataset.key);
    if (!was) return;
    if ("checked" in was) el.checked = was.checked; else el.value = was.value;
  });
  if (focusKey) {
    const el = [...root.querySelectorAll("[data-key]")].find((e) => e.dataset.key === focusKey);
    if (el) {
      el.focus({ preventScroll: true });
      if (sel) try { el.setSelectionRange(sel[0], sel[1]); } catch { /* not a text field */ }
    }
  }
  main.scrollTop = top;
}

function placeholder(root, step, data, ctx) {
  const job = data?.job;
  const st = job?.steps?.[step]?.state || "pending";
  const name = ctx.folder.split("/").filter(Boolean).pop();
  root.append(...[  // filtered: the DOM's append would write a null as the text "null"
    h("div", { class: "crumbs" }, t("page.crumb", { name, n: STEPS.indexOf(step) + 1 })),
    h("div", { class: "head" }, h("div", {}, h("h1", {}, stepTitle(step)),
      job?.steps?.[step]?.note ? h("p", {}, job.steps[step].note) : null), stepChip(st)),
    job?.gate && job.gate.step === step ? gateBar(job.gate, ctx) : null,
    h("section", { class: "card coming" }, h("h2", {}, t("app.coming_h")), h("p", {}, t("app.coming_p", { step: stepTitle(step) })))].filter(Boolean));
}

function errorCard(root, title, text) {
  root.append(h("section", { class: "card coming", role: "alert" }, h("h2", {}, title), h("p", {}, text)));
}

async function renderPage() {
  const my = ++renderSeq;
  const route = state.route;
  const view = $("#view");
  const name = route.page === "job" ? route.step : route.page;
  if (route.page === "job" && !route.step) {
    if (state.data) location.replace(jobHash(state.folder, activeStep(state.data.job)));
    else if (state.jobError) draw(() => errorCard(view, t("app.cant_open"), jobErrorText(state.jobError)));
    else draw(() => view.append(h("p", { class: "hint" }, t("common.loading"))));
    return;
  }
  const mod = await loadModule(name);
  if (my !== renderSeq) return;
  document.title = titled(`${route.page === "job" ? stepTitle(name) : t(route.page === "settings" ? "shell.title_settings" : "shell.dashboard")} · Edit Mo To`);
  draw(() => {
    const ctx = makeCtx(state.folder);
    if (route.page === "job" && !state.data) {
      if (state.jobError) errorCard(view, t("app.cant_open"), jobErrorText(state.jobError));
      else view.append(h("p", { class: "hint" }, t("common.loading")));
      return;
    }
    try {
      if (!mod?.render) {
        if (route.page === "job") placeholder(view, name, state.data, ctx);
        else errorCard(view, t("app.coming_h"), t("app.coming_later"));
      } else {
        const done = mod.render(view, state.data, ctx);
        cleanup = typeof done === "function" ? done : null;
      }
    } catch (e) {
      console.error(e);
      errorCard(view, t("app.page_error"), e.message || String(e));
    }
  });
}

function draw(fn) {
  const view = $("#view");
  keepInputs(view, () => {
    if (cleanup) { try { cleanup(); } catch { /* ignore */ } cleanup = null; }
    view.replaceChildren();
    fn();
  });
}

function changed() {
  renderShell();
  if (state.route.page === "job") renderPage();
}

function onRoute() {
  const before = state.route;
  state.route = parseRoute();
  if (state.route.page === "job") setFolder(state.route.folder);
  else if (state.current !== state.folder) setFolder(state.current);
  renderShell();
  if (before.page !== state.route.page || before.step !== state.route.step || before.folder !== state.route.folder) {
    $("#page").scrollTop = 0;
  }
  renderPage();
  closeRail();
}

// ---------- rail toggle (below 1100 px) and the whole-job message box ----------

function closeRail() {
  $("#rail").classList.remove("open");
  $("#rail-toggle").setAttribute("aria-expanded", "false");
}

function setupRail() {
  const toggle = $("#rail-toggle");
  toggle.prepend(icon("panel"));
  $("#rail-close").append(icon("x"));
  toggle.addEventListener("click", () => {
    const open = $("#rail").classList.toggle("open");
    toggle.setAttribute("aria-expanded", String(open));
    if (open) $("#job-msg").focus();
  });
  $("#rail-close").addEventListener("click", () => { closeRail(); toggle.focus(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && $("#rail").classList.contains("open")) closeRail(); });

  const ta = $("#job-msg"), btn = $("#job-send"), note = $("#job-msg-note");
  const send = async () => {
    const text = ta.value.trim();
    if (!text || !state.folder) { ta.focus(); return; }
    btn.disabled = true;
    try {
      await sendEvent(state.folder, { type: "message", step: null, text });
      ta.value = "";
      note.className = "msg ok";
      note.textContent = t(state.data?.listening ? "common.sent_listening" : "common.saved_later");
    } catch (e) {
      note.className = "msg err";
      note.textContent = e.message || t("common.not_sent_moment");
    } finally {
      btn.disabled = !state.folder;
    }
  };
  btn.addEventListener("click", send);
  ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); send(); } });
}

function setupNavIcons() {
  document.querySelectorAll("[data-icon]").forEach((el) => el.append(icon(el.dataset.icon)));
}

/** The language changed: every word on screen again, now, keeping what the editor typed (draw keeps inputs). */
function relabel() {
  applyStaticWords();
  drawConn();
  renderShell();
  renderPage();
}

async function start() {
  setupNavIcons();
  setupRail();
  await loadPrefs(api);  // before the first render, so the page opens in the editor's language
  applyStaticWords();
  onLangChange(relabel);
  window.addEventListener("hashchange", onRoute);
  await refreshCurrent();
  onRoute();
  setInterval(refreshCurrent, CURRENT_MS);
  setInterval(() => { if (!$("#working")?.hidden) renderWorking(); }, 15000);  // the time left counts down
  // Edge and Chrome slow a background tab's timers (down to once a minute): coming back from Claude's window, catch up now
  const catchUp = () => { if (document.visibilityState === "visible") { kick(); refreshCurrent(); } };
  document.addEventListener("visibilitychange", catchUp);
  window.addEventListener("focus", catchUp);
}

start();
