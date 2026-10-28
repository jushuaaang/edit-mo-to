// Settings & setup: machine.json paths (found / missing, Save), the app's language (Auto / English / Taglish), the
// alert switches, the models Claude picks (avoid list and Claude's default, from generators.json), setup checks, Report a bug / Suggest an improvement (saved on this computer; Send to Joshua opens a
// pre-filled issue).
import { h, chip, checksTable, STEPS, stepTitle } from "../ui.js";
import { t, parts } from "../words.js";
import { savePrefs, langOf } from "../nextstep.js";

const PATHS = [  // machine.json key -> its label (WORDS.set.*)
  ["root", "set.path_root"], ["python", "set.path_python"], ["tmp", "set.path_tmp"],
  ["mcp_servers", "set.path_mcp"], ["capcut_drafts", "set.path_drafts"],
];
const LANG_PREF = "ui_lang";  // auto | en | tl
const LANGS = [["auto", "settings.lang_auto"], ["en", "settings.lang_en"], ["tl", "settings.lang_tl"]];

function dateText(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function pathsCard(ctx, msgOut) {
  const body = h("tbody", {}, h("tr", {}, h("td", { colspan: "3" }, h("p", { class: "hint" }, t("common.loading")))));
  const where = h("p", {}, ...parts("set.saved_to", { file: h("span", { class: "mono" }, "machine.json") }));
  const running = h("p", { class: "hint", style: "margin-top:10px" });
  let loaded = null;

  const fill = (s) => {
    loaded = s;
    where.replaceChildren(...parts("set.saved_to", { file: h("span", { class: "mono" }, s.config) }));
    body.replaceChildren(...PATHS.map(([key, label]) => {
      const id = `set-${key}`;
      return h("tr", {},
        h("td", {}, h("label", { for: id }, t(label)), h("div", { class: "note mono" }, key)),
        h("td", { style: "width:62%" }, h("input", { class: "f mono", id, value: s.paths[key] || "", "data-key": `set:${key}`,
          spellcheck: "false", autocomplete: "off" })),
        h("td", {}, chip(t(s.found[key] ? "set.found" : "set.missing"), s.found[key] ? "ok" : "err")));
    }), h("tr", {},
      h("td", {}, h("label", { for: "set-gui_port" }, t("set.port")), h("div", { class: "note mono" }, "gui_port")),
      h("td", {}, h("input", { class: "f mono", id: "set-gui_port", type: "number", min: "1024", max: "65535",
        value: String(s.paths.gui_port || ""), "data-key": "set:gui_port", style: "max-width:140px" })),
      h("td", {})));
    running.textContent = t("set.running", { root: s.running.root, port: s.running.port });
  };

  const save = async () => {
    if (!loaded) return;
    const update = {};
    for (const [key] of PATHS) {
      const v = document.getElementById(`set-${key}`).value.trim();
      if (v !== (loaded.paths[key] || "")) update[key] = v;
    }
    const port = document.getElementById("set-gui_port").value.trim();
    if (port !== String(loaded.paths.gui_port || "")) update.gui_port = Number(port);
    if (!Object.keys(update).length) { msgOut(t("common.nothing_changed"), "ok"); return; }
    try {
      fill(await ctx.api("/api/settings", { body: update }));
      msgOut(t("settings.saved"), "ok");
    } catch (e) {
      msgOut(e.message, "err");
    }
  };

  ctx.api("/api/settings").then(fill).catch((e) => msgOut(e.message, "err"));
  return { save, node: h("section", { class: "card" }, h("h3", {}, t("set.paths_h")), where,
    h("div", { class: "tablewrap", style: "margin-top:10px" }, h("table", {},
      h("thead", {}, h("tr", {}, h("th", { scope: "col" }, t("set.th_path")), h("th", { scope: "col" }, t("set.th_value")),
        h("th", { scope: "col" }, t("set.th_found")))),
      body)), running) };
}

function checksCard(ctx) {
  const box = h("div", {}, h("p", { class: "hint" }, t("common.checking")));
  const run = () => ctx.api("/api/checks").then((c) => box.replaceChildren(checksTable(c)))
    .catch((e) => box.replaceChildren(h("p", { class: "msg err" }, e.message)));
  run();
  return h("section", { class: "card" }, h("div", { class: "row spread", style: "margin-bottom:10px" },
    h("h3", { style: "margin:0" }, t("checks.title")), h("button", { class: "btn sm", type: "button", onclick: run }, t("checks.again"))), box);
}

/** "Language: Auto / English / Taglish" (ui_lang, this computer only). Auto follows the language Claude detected in
 *  what the editor writes (ui_lang_detected); a pick here wins. The whole app re-renders in the new language at once
 *  (app.js listens), so this card only shows what the server holds. */
function langCard(ctx) {
  const msg = h("div", { class: "msg", role: "status" }, t("settings.loading"));
  const hint = h("p", { class: "hint" });
  let current = null;
  const btns = LANGS.map(([value, key]) => h("button", { type: "button", role: "radio", "aria-checked": "false",
    disabled: true, "data-lang": value, onclick: () => pick(value) }, t(key)));
  const show = (p) => {
    current = p[LANG_PREF];
    btns.forEach((b, i) => { b.setAttribute("aria-checked", String(LANGS[i][0] === current)); b.disabled = false; });
    const shown = langOf(p) === "tl" ? t("settings.lang_tl") : t("settings.lang_en");
    hint.textContent = current === "auto" ? t("settings.lang_auto_hint", { lang: shown }) : t("settings.lang_manual_hint");
  };
  const pick = async (value) => {
    if (value === current) return;
    btns.forEach((b) => { b.disabled = true; });
    try {
      show(await savePrefs(ctx.api, { [LANG_PREF]: value }));  // a new language re-renders the page from app.js
      msg.className = "msg ok";
      msg.textContent = t("settings.saved");
    } catch (e) {
      btns.forEach((b) => { b.disabled = false; });
      msg.className = "msg err";
      msg.textContent = t("settings.not_saved", { why: e.message || "" });
    }
  };
  const seg = h("div", { class: "seg", role: "radiogroup", "aria-labelledby": "lang-h" }, btns);
  seg.addEventListener("keydown", (e) => {  // arrow keys move between the options
    if (!["ArrowLeft", "ArrowRight"].includes(e.key)) return;
    const i = LANGS.findIndex(([v]) => v === current);
    const next = btns[(i + (e.key === "ArrowRight" ? 1 : LANGS.length - 1)) % LANGS.length];
    next.click();
    next.focus();
  });
  ctx.api("/api/prefs").then((p) => { show(p); msg.textContent = ""; })
    .catch((e) => { msg.className = "msg err"; msg.textContent = e.message; });
  return h("section", { class: "card", "aria-labelledby": "lang-h" },
    h("h3", { id: "lang-h" }, t("settings.lang_h")), h("p", { class: "hint" }, t("settings.lang_p")), seg, hint, msg);
}

/** "Tell me when Claude needs me": two switches saved on this computer (POST /api/prefs). A switch shows only what the
 *  server holds: it is disabled until the prefs load, and goes back if a save fails. */
function alertsCard(ctx) {
  const msg = h("div", { class: "msg", role: "status" }, t("settings.loading"));
  const blocked = h("p", { class: "hint", hidden: !("Notification" in window && Notification.permission === "denied") },
    t("settings.notify_blocked"));
  const row = (key, hint) => {
    const id = `pref-${key}`;
    const box = h("input", { type: "checkbox", role: "switch", id, class: "switch", disabled: true, "data-pref": key });
    box.addEventListener("change", async () => {
      const want = box.checked;
      box.disabled = true;
      try {
        const now = await savePrefs(ctx.api, { [key]: want });
        box.checked = now[key];
        msg.className = "msg ok";
        msg.textContent = t("settings.saved");
      } catch (e) {
        box.checked = !want;
        msg.className = "msg err";
        msg.textContent = t("settings.not_saved", { why: e.message || "" });
      } finally {
        box.disabled = false;
      }
    });
    return [box, h("div", { class: "field switchrow" }, box, h("div", {}, h("label", { class: "lbl", for: id }, t(`settings.${key}`)),
      h("div", { class: "hint" }, t(hint))))];
  };
  const [notify, notifyRow] = row("notify", "settings.notify_hint");
  const [sound, soundRow] = row("sound", "settings.sound_hint");
  ctx.api("/api/prefs").then((p) => {
    notify.checked = p.notify;
    sound.checked = p.sound;
    notify.disabled = sound.disabled = false;
    msg.textContent = "";
  }).catch((e) => { msg.className = "msg err"; msg.textContent = e.message; });
  return h("section", { class: "card", "aria-labelledby": "alerts-h" },
    h("h3", { id: "alerts-h" }, t("settings.alerts_h")), h("p", { class: "hint" }, t("settings.alerts_p")),
    h("div", { class: "stack" }, notifyRow, blocked, soundRow), msg);
}

/** "Models Claude picks" (this computer only; spec "Models Claude avoids, per editor"): every model in generators.json
 *  (GET /api/generators; no list in this page) with a "When Claude picks, never use" box (avoid_models), and "Claude's
 *  default model" (default_model), which never offers an avoided model. Ticking the current default also clears it,
 *  in the same save. The editor can still choose any model on the B-roll & prompts page. */
function modelsCard(ctx) {
  const msg = h("div", { class: "msg", role: "status" }, t("settings.loading"));
  const body = h("tbody");
  const sel = h("select", { class: "f", id: "pref-default_model", disabled: true, style: "max-width:340px" });
  let rows = [];     // [["<site>:<model>", "<site label> · <model label>"]], in table order
  let prefs = null;
  const say = (text, kind) => { msg.className = `msg ${kind}`; msg.textContent = text; };
  const show = (p) => {
    prefs = p;
    const avoid = new Set(Array.isArray(p.avoid_models) ? p.avoid_models : []);
    body.replaceChildren(...rows.map(([id, name], i) => {
      const box = h("input", { type: "checkbox", id: `avoid-${i}`, "data-model": id, checked: avoid.has(id) });
      box.addEventListener("change", () => toggle(id, box.checked));
      return h("tr", {}, h("td", {}, h("label", { for: box.id }, name)), h("td", {}, box));
    }));
    sel.replaceChildren(h("option", { value: "" }, t("settings.no_default")),
      ...rows.filter(([id]) => !avoid.has(id)).map(([id, name]) => h("option", { value: id }, name)));
    sel.value = p.default_model && !avoid.has(p.default_model) ? p.default_model : "";
    sel.disabled = false;
  };
  const save = async (patch) => {
    sel.disabled = true;
    body.querySelectorAll("input").forEach((b) => { b.disabled = true; });
    try {
      show(await savePrefs(ctx.api, patch));
      say(t("settings.saved"), "ok");
    } catch (e) {
      show(prefs);   // back to what the server holds
      say(t("settings.not_saved", { why: e.message || "" }), "err");
    }
  };
  const toggle = (id, on) => {
    const now = new Set(prefs.avoid_models || []);
    if (on) now.add(id); else now.delete(id);
    const list = rows.map(([i]) => i).filter((i) => now.has(i));
    save(on && prefs.default_model === id ? { avoid_models: list, default_model: null } : { avoid_models: list });
  };
  sel.addEventListener("change", () => save({ default_model: sel.value || null }));
  Promise.all([ctx.api("/api/generators"), ctx.api("/api/prefs")]).then(([g, p]) => {
    rows = Object.entries(g?.generators || {}).flatMap(([site, s]) => Object.entries(s?.models || {})
      .map(([m, row]) => [`${site}:${m}`, `${String(s?.label ?? site)} · ${String(row?.label ?? m)}`]));
    if (!rows.length) { say(t("prompts.no_table"), "err"); return; }
    show(p);
    msg.textContent = "";
  }).catch((e) => say(e.message, "err"));
  return h("section", { class: "card", "aria-labelledby": "models-h" },
    h("h3", { id: "models-h" }, t("settings.models_h")), h("p", { class: "hint" }, t("settings.models_p")),
    h("div", { class: "tablewrap", style: "margin-top:10px" }, h("table", {},
      h("thead", {}, h("tr", {}, h("th", { scope: "col" }, t("settings.th_model")), h("th", { scope: "col" }, t("settings.avoid")))),
      body)),
    h("div", { class: "field", style: "margin-top:14px" }, h("label", { class: "lbl", for: "pref-default_model" }, t("settings.default_model")),
      sel, h("div", { class: "hint" }, t("settings.default_hint"))),
    msg);
}

function feedbackCard(ctx) {
  let type = "bug";
  const seg = h("div", { class: "seg", role: "radiogroup", "aria-label": t("fb.type") });
  const kinds = [["bug", "fb.bug"], ["suggestion", "fb.suggest"]];
  const btns = kinds.map(([value, label]) => h("button", { type: "button", role: "radio", "aria-checked": String(value === type),
    onclick: () => { type = value; btns.forEach((b, i) => b.setAttribute("aria-checked", String(kinds[i][0] === type))); } }, t(label)));
  seg.append(...btns);
  seg.addEventListener("keydown", (e) => {  // arrow keys move between the two options
    if (!["ArrowLeft", "ArrowRight"].includes(e.key)) return;
    const next = btns[(kinds.findIndex(([v]) => v === type) + 1) % 2];
    next.click();
    next.focus();
  });
  const title = h("input", { class: "f", id: "fb-title", maxlength: "200", "data-key": "fb:title", autocomplete: "off" });
  const text = h("textarea", { class: "f", id: "fb-text", rows: 5, maxlength: "20000", "data-key": "fb:text",
    placeholder: t("fb.what") });
  const step = h("select", { class: "f", id: "fb-step", "data-key": "fb:step", style: "max-width:260px" },
    h("option", { value: "" }, t("fb.no_step")), STEPS.map((s, i) => h("option", { value: s }, `${i + 1} · ${stepTitle(s)}`)));
  const msg = h("div", { class: "msg", role: "status" });
  const list = h("ul", { class: "reports", "aria-label": t("fb.saved_h") });

  const loadList = () => ctx.api("/api/feedback").then((items) => {
    const rows = [...(items || [])].reverse();
    list.replaceChildren(...(rows.length ? rows.map((r) => h("li", {},
      h("time", { datetime: r.at }, dateText(r.at)), chip(t(r.type === "bug" ? "fb.bug_chip" : "fb.suggestion_chip"), r.type === "bug" ? "err" : "opt"),
      h("span", {}, r.title), r.step ? h("span", { class: "hint" }, `· ${stepTitle(r.step)}`) : null))
      : [h("li", { class: "hint" }, t("fb.none"))]));
  }).catch((e) => list.replaceChildren(h("li", { class: "msg err" }, e.message)));

  const submit = async (open) => {
    msg.className = "msg";
    if (!title.value.trim() || !text.value.trim()) {
      msg.className = "msg err";
      msg.textContent = t("fb.need");
      (title.value.trim() ? text : title).focus();
      return;
    }
    const entry = { type, title: title.value.trim(), text: text.value.trim() };
    if (step.value) entry.step = step.value;
    const popup = open ? window.open("", "_blank") : null;  // opened in the click, so it is not blocked
    try {
      const saved = await ctx.api("/api/feedback", { body: entry });
      title.value = "";
      text.value = "";
      step.value = "";
      msg.className = "msg ok";
      if (open) {
        if (popup) {
          popup.opener = null;
          popup.location.href = saved.issue_url;
        }
        msg.replaceChildren(`${t("fb.saved_local")} `, `${t(popup ? "fb.issue_opened" : "fb.blocked")} `,
          h("a", { href: saved.issue_url, target: "_blank", rel: "noopener noreferrer" }, t("fb.open_issue")));
      } else {
        msg.textContent = t("fb.saved_file");
      }
      loadList();
    } catch (e) {
      if (popup) popup.close();
      msg.className = "msg err";
      msg.textContent = e.message;
    }
  };

  loadList();
  return h("section", { class: "card", "aria-labelledby": "fb-h" },
    h("h3", { id: "fb-h" }, t("fb.h")),
    h("p", { class: "hint", style: "margin-bottom:14px" }, t("fb.p")),
    h("div", { class: "form" },
      seg,
      h("div", {}, h("label", { class: "lbl", for: "fb-title" }, t("fb.title")), title),
      h("div", {}, h("label", { class: "lbl", for: "fb-text" }, t("fb.what")), text),
      h("div", {}, h("label", { class: "lbl", for: "fb-step" }, t("fb.step")), step),
      h("div", { class: "row" }, h("button", { class: "btn", type: "button", onclick: () => submit(false) }, t("common.save")),
        h("button", { class: "btn pri", type: "button", onclick: () => submit(true) }, t("fb.send")))),
    msg,
    h("h4", { class: "section-h" }, t("fb.saved_h")), list);
}

export function render(root, data, ctx) {
  const msg = h("div", { class: "msg", role: "status" });
  const say = (text, kind) => { msg.className = `msg ${kind || ""}`; msg.textContent = text; };
  const paths = pathsCard(ctx, say);
  root.append(
    h("div", { class: "head" }, h("div", {}, h("h1", {}, t("shell.settings")), h("p", {}, t("set.sub"))),
    h("div", { style: "text-align:right" }, h("button", { class: "btn pri", type: "button", onclick: paths.save }, t("common.save")), msg)),
    h("div", { class: "stack" }, langCard(ctx), paths.node, alertsCard(ctx), modelsCard(ctx), checksCard(ctx), feedbackCard(ctx)));
}
