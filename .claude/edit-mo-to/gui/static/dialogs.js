// Dialogs (spec "Dialogs"): confirmations, blocking warnings and close-ups only; gates stay on the pages.
// open(name, args, ctx) is called by app.js openDialog. Every body is built from DOM nodes with h(), so data
// (names, paths, prompts, transcripts) reaches the DOM as text only. The `shot` dialog belongs to the storyboard page.
import { h, chip, dialog, toast, copyButton, dropZone, pendingChip, helpTip, timeText, STALE_TEXT } from "./ui.js";
import { t, label } from "./words.js";
import { boardItems, isClient, promptOf } from "./board.js";
import { keyframeUrl, commentsFor, statusOf, shotText, sendEvent } from "./pages/storyboard.js";

const CAPCUT_RECHECK_MS = 2000;
const baseName = (p) => String(p ?? "").split(/[\\/]/).pop();
const promptText = (row) => (typeof row?.prompt === "string" && row.prompt.trim() ? row.prompt : null);  // never the cells
const p = (...kids) => h("p", {}, ...kids);

function fieldRow(label, id, input, extra) {
  return h("div", { class: "field" }, h("label", { class: "lbl", for: id }, label), input, extra || null);
}

// ---------- New video ----------

function newVideo(args, ctx) {
  const client = h("input", { class: "f", id: "nv-client", autocomplete: "off" });
  const product = h("input", { class: "f", id: "nv-product", autocomplete: "off" });
  const folder = h("input", { class: "f mono", id: "nv-folder", autocomplete: "off", spellcheck: "false" });
  const link = h("input", { class: "f mono", id: "nv-link", autocomplete: "off", spellcheck: "false", placeholder: "https://… (optional)" });
  const where = h("div", { class: "hint", role: "status" });
  const msg = h("div", { class: "msg", role: "status" });
  let root = "", known = new Map(), touched = false;

  const check = () => {
    const name = folder.value.trim();
    if (!name) { where.textContent = root ? `Goes in ${root}/` : ""; return; }
    const found = known.get(name);
    where.replaceChildren(root ? h("span", { class: "mono" }, `${root}/${name}`) : name, " ",
      found === undefined ? chip("will be created", "wait") : found.has_job ? chip("already has a job", "err") : chip("found", "ok"));
  };
  const suggest = () => {
    if (touched) return;
    folder.value = [client.value.trim(), product.value.trim()].filter(Boolean).join(" ");
    check();
  };
  client.addEventListener("input", suggest);
  product.addEventListener("input", suggest);
  folder.addEventListener("input", () => { touched = true; check(); });
  (async () => {
    try {
      const [s, jobs] = await Promise.all([ctx.api("/api/settings"), ctx.api("/api/jobs")]);
      root = String(s?.running?.root || "").replace(/\\/g, "/").replace(/\/+$/, "");
      known = new Map((jobs || []).filter((j) => !j.practice).map((j) => [j.name, j]));
    } catch { /* the server checks again on Create */ }
    check();
  })();

  const create = async (close) => {
    const body = { client: client.value.trim(), product: product.value.trim(), folder: folder.value.trim() };
    if (!body.client) { client.focus(); return; }
    if (!body.product) { product.focus(); return; }
    if (!body.folder) { folder.focus(); return; }
    if (/[\\/]/.test(body.folder) || /^[._]/.test(body.folder)) {
      msg.className = "msg err";
      msg.textContent = "Use a plain folder name (no slashes, not starting with . or _). It goes directly in the video folders root.";
      return;
    }
    msg.className = "msg";
    msg.textContent = "Creating…";
    try {
      const res = await ctx.api("/api/new", { body });
      const url = link.value.trim();
      if (url) {
        await ctx.api("/api/inbox", { body: { folder: res.folder, event: {
          type: "answer", step: "brief", gate: null, target: "brief:link", value: url, early: true } } });
      }
      close();
      ctx.go(`#/job/${encodeURIComponent(res.folder)}/brief`);
    } catch (e) {
      msg.className = "msg err";
      msg.textContent = e.message || "The video could not be created.";
    }
  };

  return dialog("new", h("div", { class: "stack" },
    p("Claude starts the brief when you run /edit-mo-to on this folder in Claude Code."),
    fieldRow("Client", "nv-client", client), fieldRow("Product", "nv-product", product),
    fieldRow("Folder", "nv-folder", folder, where), fieldRow("Brief link", "nv-link", link), msg),
  [{ label: "Cancel" }, { label: "Create video", primary: true, keepOpen: true, onClick: create }], { title: "New video" });
}

// ---------- CapCut is still running ----------

function capcut(args, ctx) {
  const status = h("p", { role: "status" }, "Checking again every 2 seconds…");
  let done = false;
  const recheck = async () => {
    if (done) return;
    try {
      const r = await ctx.api("/api/capcut");
      if (r && !r.running && !done) {
        done = true;
        d.close();
        if (args?.onClosed) args.onClosed();
      } else if (!done) {
        status.textContent = `Still running (checked ${new Date().toLocaleTimeString()}). Checking again every 2 seconds…`;
      }
    } catch (e) {
      status.textContent = e.message || "Could not check CapCut.";
    }
  };
  const d = dialog("capcut", h("div", { class: "stack" },
    p("CapCut rewrites its projects when it closes, so a change written now would be lost. Quit CapCut completely "
      + "(not just the window), then Claude writes."),
    status),
  [{ label: "Cancel this change", onClick: () => { done = true; if (args?.onCancel) args.onCancel(); } },
    { label: "I quit it, check again", primary: true, keepOpen: true, onClick: recheck }],
  { title: "CapCut is still running" });
  const timer = setInterval(recheck, CAPCUT_RECHECK_MS);
  d.el.addEventListener("close", () => { done = true; clearInterval(timer); });
  return d;
}

// ---------- Project name already taken ----------

function projectName(args, ctx) {
  const { gate, q } = args || {};
  const suggestion = typeof q?.default === "string" && q.default ? q.default : `${args?.product || "Project"} 2`;
  const input = h("input", { class: "f", id: "pn-name", value: suggestion, autocomplete: "off" });
  const msg = h("div", { class: "msg", role: "status" });
  const send = async (close) => {
    const name = input.value.trim();
    if (!name) { input.focus(); return; }
    try {
      const ev = await ctx.send({ type: "answer", step: gate?.step || "build", gate: gate?.id || null, target: q?.id || "project_name", value: name });
      if (ev?.stale) { msg.className = "msg err"; msg.textContent = STALE_TEXT; return; }
      close();
    } catch (e) {
      msg.className = "msg err";
      msg.textContent = e.message || "Not sent. Try again.";
    }
  };
  return dialog("name", h("div", { class: "stack" },
    p(q?.text ? String(q.text) : "A CapCut project with this name already exists."),
    p("Pick another name. Claude never overwrites an existing project."),
    fieldRow("New project name", "pn-name", input), msg),
  [{ label: "Later" }, { label: "Use this name", primary: true, keepOpen: true, onClick: send }],
  { title: "Project name already taken" });
}

// ---------- Contact sheet ----------

function contact(args, ctx) {
  const row = args?.row || {};
  const id = String(row.id ?? "");
  const decide = (value) => async () => {
    try {
      await ctx.send({ type: "edit", step: "clips", target: `clips:${id}`, value });
      toast(ctx.data?.listening ? "Sent. Claude is on it." : "Saved, waiting for Claude");
    } catch (e) {
      toast(e.message || "Not sent. Try again.");
    }
  };
  const sheet = typeof row.sheet === "string" && row.sheet
    ? h("img", { class: "sheet", src: `/api/file?path=${encodeURIComponent(row.sheet)}`, alt: `Frames of ${id}`,
      onerror: (e) => e.target.replaceWith(h("p", { class: "hint" }, `The contact sheet ${baseName(row.sheet)} can't be opened any more.`)) })
    : h("p", { class: "hint" }, "No contact sheet in this report. Claude can open it from the clip check folder.");
  return dialog("contact", h("div", { class: "stack" },
    h("div", { class: "row" }, h("span", { class: "mono" }, baseName(id)), chip("FLAG", "err")),
    sheet,
    h("ul", { class: "files" }, (row.cells || []).slice(1).map((c) => h("li", {}, String(c)))),
    row.note ? p(String(row.note)) : null,
    promptText(args?.prompt) ? h("div", { class: "row" }, copyButton(promptText(args.prompt), "Copy prompt"),
      h("span", { class: "hint" }, t("prompts.regen", { name: label(args.prompt.id) })))
      : h("p", { class: "hint" }, "No step-6 prompt matches this clip, so there is nothing to copy here.")),
  [{ label: "Mark for regenerate", onClick: decide("regenerate") }, { label: "Use anyway", primary: true, onClick: decide("use") }],
  { title: "Contact sheet", wide: true });
}

// ---------- Reuse an older VO ----------

function oldVo(args, ctx) {
  const data = ctx.data;
  const gate = data?.job?.gate?.step === "voiceover" ? data.job.gate : null;
  const files = (data?.events || []).filter((e) => e.type === "upload" && e.step === "voiceover" && typeof e.value === "string");
  const pick = h("select", { class: "f", id: "ov-file" }, h("option", { value: "" }, "Choose a file you added…"),
    files.map((e) => h("option", { value: e.value }, baseName(e.value))));
  const path = h("input", { class: "f mono", id: "ov-path", placeholder: "…or the full path of the older VO", spellcheck: "false" });
  const msg = h("div", { class: "msg", role: "status" });
  const transcribe = h("button", { class: "btn", type: "button" }, "Ask Claude to transcribe it");
  transcribe.addEventListener("click", async () => {
    const file = path.value.trim() || pick.value;
    if (!file) { path.focus(); return; }
    try {
      await ctx.send({ type: "action", step: "voiceover", target: "voiceover:oldvo-transcribe", value: file });
      msg.className = "msg ok";
      msg.textContent = "Saved. The sentences show here once Claude has transcribed it.";
    } catch (e) {
      msg.className = "msg err";
      msg.textContent = e.message || "Not sent. Try again.";
    }
  });

  const t = data?.outputs?.voiceover?.oldvo;
  const tls = Array.isArray(data?.job?.card?.timelines) ? data.job.card.timelines : [];
  const rows = Array.isArray(t?.rows) ? t.rows : [];
  const ticks = rows.map(() => h("input", { type: "checkbox" }));
  const assign = rows.map(() => h("select", { class: "f" }, h("option", { value: "" }, "Timeline…"), tls.map((n) => h("option", { value: n }, n))));
  const list = rows.length ? h("div", { class: "tablewrap" }, h("table", {},
    h("thead", {}, h("tr", {}, h("th", {}, h("span", { class: "sr" }, "Use")), (t.columns || []).map((c) => h("th", { scope: "col" }, String(c))),
      h("th", { scope: "col" }, "Timeline"))),
    h("tbody", {}, rows.map((r, i) => h("tr", {}, h("td", {}, h("label", { class: "sr" }, `Use ${String(r.id)}`), ticks[i]),
      (r.cells || []).map((c) => h("td", {}, String(c))), h("td", {}, assign[i])))))) : null;

  const send = async (close) => {
    const picks = rows.map((r, i) => ({ id: String(r.id), timeline: assign[i].value || null })).filter((_, i) => ticks[i].checked);
    if (!picks.length) { msg.className = "msg err"; msg.textContent = "Tick the sentences to use first."; return; }
    try {
      const ev = await ctx.send(gate ? { type: "answer", step: "voiceover", gate: gate.id, target: "oldvo", value: picks }
        : { type: "answer", step: "voiceover", gate: null, target: "voiceover:oldvo", value: picks });
      if (ev?.stale) { msg.className = "msg err"; msg.textContent = STALE_TEXT; return; }
      close();
      toast(ctx.data?.listening ? "Sent. Claude is listening." : "Saved. Claude reads it when it next checks.");
    } catch (e) {
      msg.className = "msg err";
      msg.textContent = e.message || "Not sent. Try again.";
    }
  };

  return dialog("oldvo", h("div", { class: "stack" },
    p("Reuse a VO you already have instead of making a new one. Claude transcribes it, you tick the sentences to use "
      + "and the timeline each one goes to."),
    fieldRow("Older VO", "ov-file", pick), path, h("div", { class: "row" }, transcribe),
    list || h("p", { class: "hint" }, "No transcript yet."), msg),
  rows.length ? [{ label: "Cancel" }, { label: "Use these sentences", primary: true, keepOpen: true, onClick: send }] : [{ label: "Close" }],
  { title: "Reuse an older VO", wide: true });
}

// ---------- Change in place? ----------

function inPlace(args, ctx) {
  const where = h("span", { class: "mono" }, "edit-mo-to-backups/ in the CapCut project");
  (async () => {
    try {
      const s = await ctx.api("/api/settings");
      const drafts = String(s?.paths?.capcut_drafts || "").replace(/\\/g, "/").replace(/\/+$/, "");
      if (drafts && args?.project) where.textContent = `${drafts}/${args.project}/edit-mo-to-backups/`;
    } catch { /* keep the general wording */ }
  })();
  const names = (args?.timelines || []).map(String).filter(Boolean);
  return dialog("inplace", h("div", { class: "stack" },
    p("Claude changes ", h("b", {}, names.length ? names.join(", ") : "the timeline"), " in place. "
      + "A backup of each timeline is saved first, in:"),
    where,
    p("Or keep the original untouched and Claude makes a new timeline with the change.")),
  [{ label: "Cancel" }, { label: "Make a new timeline", onClick: () => args?.onNew?.() },
    { label: "Change in place", primary: true, onClick: () => args?.onInPlace?.() }],
  { title: "Change in place?" });
}

// ---------- Learning step ----------

function learn(args, ctx) {
  const t = args?.table || {};
  const rows = Array.isArray(t.rows) ? t.rows : [];
  const items = rows.map((r) => {
    const id = String(r.id ?? "");
    const text = (r.cells || []).map(String).filter(Boolean).join(" · ");
    const scope = h("select", { class: "f", "aria-label": `Where to keep ${id}` },
      h("option", { value: "general" }, "General rule (my preferences)"), h("option", { value: "client" }, "Client note"));
    if (/client/i.test(text)) scope.value = "client";
    const state = h("span", { role: "status" });
    const decide = (decision) => async () => {
      try {
        await ctx.send({ type: "answer", step: "export", gate: null, target: `learn:${id}`, value: { decision, scope: scope.value } });
        state.replaceChildren(chip(decision === "save" ? "Saved · waiting for Claude" : "Declined", decision === "save" ? "wait" : "mute"));
      } catch (e) {
        toast(e.message || "Not sent. Try again.");
      }
    };
    return h("li", {}, h("div", {}, text), r.note ? h("div", { class: "hint" }, String(r.note)) : null,
      h("div", { class: "row", style: "margin-top:6px" }, scope,
        h("button", { class: "btn sm pri", type: "button", onclick: decide("save") }, "Save"),
        h("button", { class: "btn sm", type: "button", onclick: decide("decline") }, "Decline"), state));
  });
  return dialog("learn", h("div", { class: "stack" },
    p("Claude proposes these from this video. Save the ones that should shape the next videos; decline the rest."),
    rows.length ? h("ol", { class: "learn" }, items) : h("p", { class: "hint" }, "Nothing proposed yet.")),
  [{ label: "Done", primary: true }], { title: "Learning step", wide: true });
}

// ---------- Shot detail (storyboard) ----------

const SHOT_REFRESH_MS = 1500;

function shot(args, ctx) {
  let id = String(args?.id ?? "");
  let shownUrl = null;
  const items = () => boardItems(ctx.data);
  const current = () => items().find((it) => it.id === id) || null;
  const body = h("div", { class: "shot" });
  const imgSlot = h("div", { class: "shotimg" });

  const picture = (it) => {
    shownUrl = keyframeUrl(ctx.data, it.id);
    imgSlot.replaceChildren(shownUrl ? h("img", { src: shownUrl, alt: t("storyboard.picture_of", { name: label(it.id, ctx.data) }) })
      : h("div", { class: "sbimg empty" }, h("span", {}, isClient(it) ? "Client footage" : "No image yet"),
        h("small", {}, isClient(it) ? "no keyframe needed" : t("storyboard.save_as", { id: it.id }))));
  };

  /** A text box saved as an `edit` event (target storyboard:<id>:<field>); shows pending until Claude applies it. */
  const editField = (it, field, text, value, mono) => {
    const fid = `shot-${field}`;
    const target = `storyboard:${it.id}:${field}`;
    const ta = h("textarea", { class: `f${mono ? " mono" : ""}`, id: fid, rows: field === "prompt" ? 6 : 3 }, value || "");
    const state = h("span", { class: "row" }, (ctx.data?.pending || []).some((e) => e.target === target) ? pendingChip() : null);
    const save = h("button", { class: "btn sm pri", type: "button" }, `Save ${field === "prompt" ? "prompt" : "visual direction"}`);
    save.addEventListener("click", async () => {
      const v = ta.value.trim();
      if (!v) { ta.focus(); return; }
      save.disabled = true;
      if (await sendEvent(ctx, { type: "edit", target, value: v })) state.replaceChildren(pendingChip());
      save.disabled = false;
    });
    return h("div", { class: "field" }, h("label", { class: "lbl", for: fid }, text), field === "prompt" ? helpTip("prompt") : null, ta,
      h("div", { class: "row" }, save, field === "prompt" && promptOf(it) ? copyButton(promptOf(it), "Copy prompt") : null, state));
  };

  const commentsPart = (it) => {
    const list = commentsFor(ctx.data, it.id);
    const ta = h("textarea", { class: "f", id: "shot-comment", rows: 2, placeholder: t("storyboard.comment_dialog", { name: label(it.id, ctx.data) }) });
    const ul = h("ul", { class: "files", hidden: !list.length }, list.map((c) => h("li", {}, h("span", {}, String(c.text ?? "")),
      chip(c.open ? "open" : "Claude has it", c.open ? "you" : "ok"))));
    const btn = h("button", { class: "btn sm pri", type: "button" }, "Send comment");
    btn.addEventListener("click", async () => {
      const text = ta.value.trim();
      if (!text) { ta.focus(); return; }
      btn.disabled = true;
      if (await sendEvent(ctx, { type: "comment", target: `storyboard:${it.id}`, text })) {
        ul.append(h("li", {}, h("span", {}, text), chip("open", "you")));
        ul.hidden = false;
        ta.value = "";
      }
      btn.disabled = false;
    });
    return h("div", { class: "field" }, h("label", { class: "lbl", for: "shot-comment" }, "Comments"),
      ul, ta, h("div", { class: "row" }, btn));
  };

  const fill = () => {
    const it = current();
    const title = d.el.querySelector(".dh h2");
    if (!it) { body.replaceChildren(p("This shot is no longer on the board.")); return; }
    const [word, status] = statusOf(ctx.data, it);
    const b = it.item;
    const name = label(it.id, ctx.data);
    title.textContent = it.kind === "char" ? t("storyboard.char_title", { name }) : name;
    const list = items(), i = list.findIndex((x) => x.id === it.id);
    const [prev, next] = d.el.querySelectorAll(".df .btn");  // ← → name the shot they go to
    if (prev && list.length > 1) prev.textContent = t("storyboard.prev", { name: label(list[(i - 1 + list.length) % list.length].id, ctx.data) });
    if (next && list.length > 1) next.textContent = t("storyboard.next", { name: label(list[(i + 1) % list.length].id, ctx.data) });
    picture(it);
    body.replaceChildren(
      h("div", { class: "shotpic" }, imgSlot,
        isClient(it) ? null : dropZone("keyframe", ctx, { id: it.id, label: "Choose file", onDone: () => setTimeout(refresh, 300) })),
      h("div", { class: "stack" },
        h("div", { class: "row" }, chip(word, status), b.est ? timeText(String(b.est), { class: "mono hint" }) : null,
          h("span", { class: "hint" }, shotText(it))),
        it.kind === "char" ? h("b", {}, String(b.name ?? "")) : null,
        b.line ? h("q", { class: "sbline" }, String(b.line)) : null,
        b.en ? h("div", { class: "hint" }, `English (temporary): ${String(b.en)}`) : null,
        it.kind === "shot" ? editField(it, "visual", "Visual direction", typeof b.visual === "string" ? b.visual : "") : null,
        isClient(it) ? null : editField(it, "prompt", "Keyframe prompt", promptOf(it), true),
        !isClient(it) && !promptOf(it) && it.kind === "shot" ? h("p", { class: "hint" }, "The prompt comes after the character sheet.") : null,
        commentsPart(it)));
  };
  const refresh = () => {  // a keyframe saved from outside (or just uploaded) shows without losing what was typed
    const it = current();
    if (it && keyframeUrl(ctx.data, it.id) !== shownUrl) picture(it);
  };
  const step = (dir) => {
    const list = items();
    const i = list.findIndex((it) => it.id === id);
    if (!list.length) return;
    id = list[(i + dir + list.length) % list.length].id;
    fill();
  };
  const act = (event, word) => async () => {
    const it = current();
    if (!it) return;
    await sendEvent(ctx, { ...event(it) }, t("storyboard.acted", { word, name: label(it.id, ctx.data),
      after: ctx.data?.listening ? "Claude is on it." : "Saved, waiting for Claude." }));
  };
  const d = dialog("shot", body, [
    { label: t("storyboard.prev_plain"), keepOpen: true, onClick: () => step(-1) },
    { label: t("storyboard.next_plain"), keepOpen: true, onClick: () => step(1) },
    { label: "Request change", keepOpen: true, onClick: act((it) => ({ type: "action", target: `storyboard:${it.id}`, value: "request change",
      text: d.el.querySelector("#shot-comment")?.value.trim() || null }), "Change requested for") },
    { label: "Approve shot", primary: true, keepOpen: true, onClick: act((it) => ({ type: "approve", target: `storyboard:${it.id}` }), "Approved") },
  ], { title: "Shot", wide: true });
  d.el.addEventListener("keydown", (e) => {
    if (/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
    if (e.key === "ArrowLeft") { e.preventDefault(); step(-1); }
    if (e.key === "ArrowRight") { e.preventDefault(); step(1); }
  });
  const timer = setInterval(refresh, SHOT_REFRESH_MS);
  d.el.addEventListener("close", () => clearInterval(timer));
  fill();
  return d;
}

const DIALOGS = { new: newVideo, capcut, name: projectName, contact, oldvo: oldVo, inplace: inPlace, learn, shot };

/** Open a dialog by name: new, capcut, name, contact, oldvo, inplace, learn, shot. */
export function open(name, args, ctx) {
  const fn = DIALOGS[name];
  if (!fn) return dialog(name, h("p", {}, "This dialog arrives in a later build."), [{ label: "Close", primary: true }], { title: "Coming" });
  return fn(args || {}, ctx);
}
