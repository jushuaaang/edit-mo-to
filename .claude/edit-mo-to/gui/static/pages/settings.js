// Settings & setup: machine.json paths (found / missing, Save), setup checks,
// Report a bug / Suggest an improvement (saved on this computer; Send to Joshua opens a pre-filled issue).
import { h, chip, checksTable, STEPS, stepTitle } from "../ui.js";

const PATHS = [
  ["root", "Video folders (root)"], ["python", "Python (tools venv)"], ["tmp", "Work folder (tmp)"],
  ["mcp_servers", "MCP servers folder"], ["capcut_drafts", "CapCut drafts folder"],
];

function dateText(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function pathsCard(ctx, msgOut) {
  const body = h("tbody", {}, h("tr", {}, h("td", { colspan: "3" }, h("p", { class: "hint" }, "Loading…"))));
  const where = h("p", {}, "Saved to ", h("span", { class: "mono" }, "machine.json"), " on this computer only.");
  const running = h("p", { class: "hint", style: "margin-top:10px" });
  let loaded = null;

  const fill = (s) => {
    loaded = s;
    where.replaceChildren("Saved to ", h("span", { class: "mono" }, s.config), " on this computer only.");
    body.replaceChildren(...PATHS.map(([key, label]) => {
      const id = `set-${key}`;
      return h("tr", {},
        h("td", {}, h("label", { for: id }, label), h("div", { class: "note mono" }, key)),
        h("td", { style: "width:62%" }, h("input", { class: "f mono", id, value: s.paths[key] || "", "data-key": `set:${key}`,
          spellcheck: "false", autocomplete: "off" })),
        h("td", {}, chip(s.found[key] ? "found" : "missing", s.found[key] ? "ok" : "err")));
    }), h("tr", {},
      h("td", {}, h("label", { for: "set-gui_port" }, "GUI port"), h("div", { class: "note mono" }, "gui_port")),
      h("td", {}, h("input", { class: "f mono", id: "set-gui_port", type: "number", min: "1024", max: "65535",
        value: String(s.paths.gui_port || ""), "data-key": "set:gui_port", style: "max-width:140px" })),
      h("td", {})));
    running.textContent = `This server is running with root ${s.running.root} on port ${s.running.port}. ` +
      "Changed paths apply the next time the GUI starts.";
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
    if (!Object.keys(update).length) { msgOut("Nothing changed.", "ok"); return; }
    try {
      fill(await ctx.api("/api/settings", { body: update }));
      msgOut("Saved.", "ok");
    } catch (e) {
      msgOut(e.message, "err");
    }
  };

  ctx.api("/api/settings").then(fill).catch((e) => msgOut(e.message, "err"));
  return { save, node: h("section", { class: "card" }, h("h3", {}, "Paths"), where,
    h("div", { class: "tablewrap", style: "margin-top:10px" }, h("table", {},
      h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Path"), h("th", { scope: "col" }, "Value"), h("th", { scope: "col" }, "Found"))),
      body)), running) };
}

function checksCard(ctx) {
  const box = h("div", {}, h("p", { class: "hint" }, "Checking…"));
  const run = () => ctx.api("/api/checks").then((c) => box.replaceChildren(checksTable(c)))
    .catch((e) => box.replaceChildren(h("p", { class: "msg err" }, e.message)));
  run();
  return h("section", { class: "card" }, h("div", { class: "row spread", style: "margin-bottom:10px" },
    h("h3", { style: "margin:0" }, "Setup check"), h("button", { class: "btn sm", type: "button", onclick: run }, "Check again")), box);
}

function feedbackCard(ctx) {
  let type = "bug";
  const seg = h("div", { class: "seg", role: "radiogroup", "aria-label": "Report type" });
  const kinds = [["bug", "Report a bug"], ["suggestion", "Suggest an improvement"]];
  const btns = kinds.map(([value, label]) => h("button", { type: "button", role: "radio", "aria-checked": String(value === type),
    onclick: () => { type = value; btns.forEach((b, i) => b.setAttribute("aria-checked", String(kinds[i][0] === type))); } }, label));
  seg.append(...btns);
  seg.addEventListener("keydown", (e) => {  // arrow keys move between the two options
    if (!["ArrowLeft", "ArrowRight"].includes(e.key)) return;
    const next = btns[(kinds.findIndex(([v]) => v === type) + 1) % 2];
    next.click();
    next.focus();
  });
  const title = h("input", { class: "f", id: "fb-title", maxlength: "200", "data-key": "fb:title", autocomplete: "off" });
  const text = h("textarea", { class: "f", id: "fb-text", rows: 5, maxlength: "20000", "data-key": "fb:text",
    placeholder: "What happened, or what would make the workflow better?" });
  const step = h("select", { class: "f", id: "fb-step", "data-key": "fb:step", style: "max-width:260px" },
    h("option", { value: "" }, "Not about one step"), STEPS.map((s, i) => h("option", { value: s }, `${i + 1} · ${stepTitle(s)}`)));
  const msg = h("div", { class: "msg", role: "status" });
  const list = h("ul", { class: "reports", "aria-label": "Saved reports" });

  const loadList = () => ctx.api("/api/feedback").then((items) => {
    const rows = [...(items || [])].reverse();
    list.replaceChildren(...(rows.length ? rows.map((r) => h("li", {},
      h("time", { datetime: r.at }, dateText(r.at)), chip(r.type === "bug" ? "Bug" : "Suggestion", r.type === "bug" ? "err" : "opt"),
      h("span", {}, r.title), r.step ? h("span", { class: "hint" }, `· ${stepTitle(r.step)}`) : null))
      : [h("li", { class: "hint" }, "Nothing saved yet.")]));
  }).catch((e) => list.replaceChildren(h("li", { class: "msg err" }, e.message)));

  const submit = async (open) => {
    msg.className = "msg";
    if (!title.value.trim() || !text.value.trim()) {
      msg.className = "msg err";
      msg.textContent = "Add a title and a few words first.";
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
        msg.replaceChildren("Saved on this computer. ", popup ? "The issue page opened in your browser: check it and submit it there. "
          : "Your browser blocked the new tab. ", h("a", { href: saved.issue_url, target: "_blank", rel: "noopener noreferrer" }, "Open the issue page"));
      } else {
        msg.textContent = "Saved on this computer (feedback.jsonl). Claude can read it when you say “look at my feedback”.";
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
    h("h3", { id: "fb-h" }, "Report a bug / Suggest an improvement"),
    h("p", { class: "hint", style: "margin-bottom:14px" }, "Save keeps it on this computer. Send to Joshua also opens a pre-filled issue on GitHub " +
      "that you check and submit yourself (a GitHub account is needed). Only what you type is included, plus the edit-mo-to version, " +
      "Windows or macOS, and the step you pick. Nothing is sent automatically."),
    h("div", { class: "form" },
      seg,
      h("div", {}, h("label", { class: "lbl", for: "fb-title" }, "Title"), title),
      h("div", {}, h("label", { class: "lbl", for: "fb-text" }, "What happened, or what would make the workflow better?"), text),
      h("div", {}, h("label", { class: "lbl", for: "fb-step" }, "Which step (optional)"), step),
      h("div", { class: "row" }, h("button", { class: "btn", type: "button", onclick: () => submit(false) }, "Save"),
        h("button", { class: "btn pri", type: "button", onclick: () => submit(true) }, "Send to Joshua"))),
    msg,
    h("h4", { class: "section-h" }, "Saved reports"), list);
}

export function render(root, data, ctx) {
  const msg = h("div", { class: "msg", role: "status" });
  const say = (text, kind) => { msg.className = `msg ${kind || ""}`; msg.textContent = text; };
  const paths = pathsCard(ctx, say);
  root.append(
    h("div", { class: "head" }, h("div", {}, h("h1", {}, "Settings & setup"),
      h("p", {}, "The paths this computer uses, the setup check, and a place to report bugs.")),
    h("div", { style: "text-align:right" }, h("button", { class: "btn pri", type: "button", onclick: paths.save }, "Save"), msg)),
    h("div", { class: "stack" }, paths.node, checksCard(ctx), feedbackCard(ctx)));
}
