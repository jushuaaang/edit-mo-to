// Edit Mo To app shell: API calls, hash router, polling, the three-column layout.
//
// Routes:  #/  dashboard   ·   #/settings   ·   #/job/<encoded folder>/<step>
// Pages:   pages/<name>.js exports render(root, data, ctx); it may return a cleanup function.
//          data = the /api/job reply for the open video (or null), ctx = see ui.js header.
//          A page whose module is not there yet shows "This page is coming".

import { h, icon, stepChip, STEPS, stepTitle, relTime, gateBar, askBox, dialog, previousStep, helpTip } from "./ui.js";
import { watchQuestion, titled, loadPrefs } from "./nextstep.js";

const POLL_MS = 1500;
const CURRENT_MS = 5000;
const LISTENING_OFF = "Claude isn't listening. Your message is saved; it's picked up when Claude next checks, or type 'go' in chat. If Claude asked for permission, answer it in chat.";

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
    throw new ApiError(0, "The GUI server isn't answering. Is it still running?");
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
  if (!res.ok) throw new ApiError(res.status, data?.error || `The server said ${res.status}.`);
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
        reject(new ApiError(xhr.status, data?.error || `The upload was refused (${xhr.status}).`));
      }
    };
    xhr.onerror = () => reject(new ApiError(0, "The upload stopped. Check the file type and size, then try again."));
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
    watchQuestion(folder, data);  // pop-up, sound and "(1)" in the tab title when a new question opens
  } else {
    state.etag = null;
    state.data = null;
    state.jobError = { status: res.status, message: data?.error || "" };
  }
  changed();
}

async function refreshCurrent() {
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
  if (!folder) throw new ApiError(0, "Open a video first.");
  const ev = await api("/api/inbox", { body: { folder, event } });
  kick();
  return ev;
}

async function openDialog(name, args) {
  let mod = null;
  try { mod = await import("./dialogs.js"); } catch { mod = null; }
  if (mod?.open) return mod.open(name, args, makeCtx(state.folder));
  const text = name === "new"
    ? "<p>The New video form arrives in a later build. For now, start a new video with /edit-mo-to in Claude Code.</p>"
    : "<p>This dialog arrives in a later build.</p>";
  return dialog(name, text, [{ label: "Close", primary: true }], { title: name === "new" ? "New video" : name });
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
  $("#conn").replaceChildren(h("span", { class: `dot ${ok ? "ok" : "err"}` }),
    ok ? `Connected · ${location.host}` : "Not connected · retrying");
}

function showKeyProblem() {
  if ($("#key-problem")) return;
  $("#view").prepend(h("div", { class: "banner err", id: "key-problem", role: "alert" },
    h("b", {}, "This page needs its key."),
    h("span", {}, "Open the link the server printed (it ends in ?k=…), or start the GUI again from Claude Code.")));
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
  const tag = st === "waiting" ? ["You", "you"] : st === "working" ? ["Working", "wait"] : st === "error" ? ["Error", "err"]
    : st === "skipped" ? ["Skipped", "mute"] : optional ? ["Optional", "opt"] : open ? ["Open now", "open"] : null;
  const current = route.page === "job" && route.step === step;
  return h("a", { href: jobHash(state.folder, step), class: cls, "aria-current": current ? "page" : null },
    h("span", { class: "n", "aria-hidden": "true" }, n),
    h("span", { class: "label" }, stepTitle(step), prev ? h("small", { class: "sub" }, `Waits for: ${stepTitle(prev)}`) : null),
    st === "done" ? h("span", { class: "sr" }, ", done") : null,
    tag ? h("span", { class: `tag ${tag[1]}` }, tag[0]) : null);
}

const CARD_HELP = { temp_en: "temp_en", vo: "vo", timelines: "timeline", generator: "model" };  // ⓘ after these
const CARD_ORDER = [["client", "Client"], ["product", "Product"], ["style", "Style"], ["language", "Language"],
  ["temp_en", "TEMP_EN"], ["folder", "Folder"], ["vo", "VO"], ["generator", "Generator"], ["timelines", "Timelines"],
  ["project", "Project"]];

function tempEn(value) {
  if (!value) return null;
  if (value === "on") return ["On · delete before export", "warn"];
  if (value.startsWith("partial:")) return [`On for ${value.slice(8)} · delete before export`, "warn"];
  if (value === "removed") return ["Removed", ""];
  if (value === "off") return ["Off", ""];
  return [value, ""];
}

function renderRail() {
  const job = state.data?.job;
  const card = job?.card || {};
  const dl = $("#jobcard");
  if (!job) {
    dl.replaceChildren(h("dt", {}, "Job"), h("dd", { class: "none" }, state.folder ? "Loading…" : "No video open"));
  } else {
    const keys = [...CARD_ORDER, ...Object.keys(card).filter((k) => !CARD_ORDER.some(([c]) => c === k)).map((k) => [k, k])];
    dl.replaceChildren(...keys.flatMap(([k, label]) => {
      let v = card[k];
      if (Array.isArray(v)) v = v.join(", ");
      if (k === "temp_en") {
        const t = tempEn(v);
        return [h("dt", {}, label, helpTip("temp_en")), t ? h("dd", { class: t[1] || null }, t[0]) : h("dd", { class: "none" }, "Not set")];
      }
      return [h("dt", {}, label, CARD_HELP[k] ? helpTip(CARD_HELP[k]) : null), v ? h("dd", { class: k === "folder" ? "mono" : null }, String(v)) : h("dd", { class: "none" }, "Not yet")];
    }));
  }
  const log = (job?.log || []).slice(-20).reverse();
  $("#activity").replaceChildren(...(log.length ? log.map((e) => {
    const m = /^\s*\[([a-z]+)\]\s*/.exec(e.text || "");
    const text = m ? `${stepTitle(m[1])} · ${e.text.slice(m[0].length)}` : e.text;
    return h("li", {}, h("time", { datetime: e.at, title: e.at }, relTime(e.at)), h("span", {}, text));
  }) : [h("li", {}, job ? "Nothing yet." : "Open a video to see what Claude is doing.")]));

  const lis = state.data?.listening;
  $("#listening").className = `status${lis ? " on" : ""}`;
  $("#listening").replaceChildren(h("span", { class: `pulse${lis ? "" : " off"}`, "aria-hidden": "true" }),
    h("span", {}, !state.folder ? "No video open. Open one on the Dashboard to talk to Claude about it."
      : lis ? `Claude is listening · ${stepTitle(lis.step) || "this job"}` : LISTENING_OFF));
  $("#job-send").disabled = !state.folder || !job;
}

function renderShell() {
  const route = state.route;
  document.querySelectorAll(".nav a[data-route]").forEach((a) => {
    if (a.dataset.route === route.page) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
  const job = state.data?.job;
  const name = state.folder ? state.folder.split("/").filter(Boolean).pop() : "";
  $("#job-name").textContent = name || "No video open";
  $("#job-name").title = state.folder || "";
  const steps = $("#steps");
  if (!job) {
    const msg = !state.folder ? "Open a video on the Dashboard."
      : state.jobError ? jobErrorText(state.jobError) : "Loading…";
    steps.replaceChildren(h("p", { class: "empty" }, msg));
  } else {
    steps.replaceChildren(...STEPS.map((s, i) => stepLink(s, i, job, route)));
  }
  renderRail();
}

function jobErrorText(err) {
  if (err.status === 404) return "This folder has no job yet. It appears once /edit-mo-to starts it.";
  if (err.status === 403) return "That folder isn't a video folder (a direct subfolder of the root).";
  return err.message || "This video could not be loaded.";
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
    const t = typed.get(el.dataset.key);
    if (!t) return;
    if ("checked" in t) el.checked = t.checked; else el.value = t.value;
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
    h("div", { class: "crumbs" }, `${name} · Step ${STEPS.indexOf(step) + 1}`),
    h("div", { class: "head" }, h("div", {}, h("h1", {}, stepTitle(step)),
      job?.steps?.[step]?.note ? h("p", {}, job.steps[step].note) : null), stepChip(st)),
    job?.gate && job.gate.step === step ? gateBar(job.gate, ctx) : null,
    h("section", { class: "card coming" }, h("h2", {}, "This page is coming"),
      h("p", {}, `The full ${stepTitle(step)} page arrives in a later build. Claude's questions for this step show above when it asks, and you can write to Claude below.`)),
    askBox(step, data, ctx)].filter(Boolean));
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
    else if (state.jobError) draw(() => errorCard(view, "This video can't be opened", jobErrorText(state.jobError)));
    else draw(() => view.append(h("p", { class: "hint" }, "Loading…")));
    return;
  }
  const mod = await loadModule(name);
  if (my !== renderSeq) return;
  document.title = titled(`${route.page === "job" ? stepTitle(name) : route.page === "settings" ? "Settings" : "Dashboard"} · Edit Mo To`);
  draw(() => {
    const ctx = makeCtx(state.folder);
    if (route.page === "job" && !state.data) {
      if (state.jobError) errorCard(view, "This video can't be opened", jobErrorText(state.jobError));
      else view.append(h("p", { class: "hint" }, "Loading…"));
      return;
    }
    try {
      if (!mod?.render) {
        if (route.page === "job") placeholder(view, name, state.data, ctx);
        else errorCard(view, "This page is coming", "It arrives in a later build.");
      } else {
        const done = mod.render(view, state.data, ctx);
        cleanup = typeof done === "function" ? done : null;
      }
    } catch (e) {
      console.error(e);
      errorCard(view, "This page could not be shown", e.message || String(e));
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
      note.textContent = state.data?.listening ? "Sent. Claude is listening." : "Saved. Claude reads it when it next checks.";
    } catch (e) {
      note.className = "msg err";
      note.textContent = e.message || "Not sent. Try again in a moment.";
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

async function start() {
  setupNavIcons();
  setupRail();
  loadPrefs(api);
  window.addEventListener("hashchange", onRoute);
  await refreshCurrent();
  onRoute();
  setInterval(refreshCurrent, CURRENT_MS);
}

start();
