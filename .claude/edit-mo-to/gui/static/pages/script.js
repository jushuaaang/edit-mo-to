// Script (step 3): "Use my script" or "Write one", the editable script table (with the "English (temporary)"
// column when TEMP_EN is on), Claude's script QA. "Storyboard first?" and script approval come from the gate.
// Cell edits are `edit` events (target "script:<line id>") and show "pending" until Claude applies them.
import { h, chip, pendingChip, toast, helpTip } from "../ui.js";
import { t } from "../words.js";
import { stepPage, textInput, choiceInput, outputsOf, outputTables, pendingFor, sendEdit, lastInput, waitingText } from "../steppage.js";

const ownScript = (ctx, data) => textInput(ctx, data, "script", "own_script", t("script.yours"), { rows: 8,
  placeholder: t("script.ph"), hint: t("script.hint"), button: t("script.save") });

function scriptTable(ctx, data, script) {
  const lines = script?.lines || [];
  if (!lines.length) return h("section", { class: "card" }, h("h3", {}, t("step.script")), h("p", { class: "hint" }, t("script.empty")));
  const temp = Boolean(script.temp_en);
  const cells = new Map();
  const rows = lines.map((ln) => {
    const id = String(ln.id ?? "");
    const pend = pendingFor(data, `script:${id}`).pop();
    const text = pend && typeof pend.value === "string" ? pend.value : String(ln.text ?? "");
    const ta = h("textarea", { class: "f cell", rows: "2", "data-key": `script:${id}`, "aria-label": t("script.line_label", { id }) }, text);
    cells.set(id, ta);
    return h("tr", { "data-id": id }, h("td", { class: "mono" }, id, pend ? h("div", {}, pendingChip()) : null), h("td", {}, ta),
      temp ? h("td", { class: "hint" }, String(ln.en ?? "")) : null);
  });
  const note = h("span", { class: "hint", role: "status" });
  const btn = h("button", { class: "btn pri", type: "button" }, t("script.send"));
  btn.addEventListener("click", async () => {
    const changed = [...cells].filter(([, ta]) => ta.value.trim() && ta.value !== ta.defaultValue);
    if (!changed.length) { note.textContent = t("common.nothing_changed"); return; }
    btn.disabled = true;
    try {
      for (const [id, ta] of changed) await sendEdit(ctx, "script", `script:${id}`, ta.value.trim());
      note.textContent = waitingText(data);
    } catch (e) {
      toast(e.message || t("common.not_sent"));
    } finally {
      btn.disabled = false;
    }
  });
  return h("section", { class: "card" }, h("div", { class: "row spread" }, h("h3", {}, t("step.script")),
    h("div", { class: "row" }, chip(t("script.lang", { lang: script.lang || "?" }), "mute"), temp ? chip(t("script.temp_on"), "err") : null, temp ? helpTip("temp_en") : null)),
  h("div", { class: "tablewrap" }, h("table", {}, h("thead", {}, h("tr", {}, h("th", { scope: "col" }, t("script.th_id")),
    h("th", { scope: "col" }, t("script.th_line")), temp ? h("th", { scope: "col" }, t("script.th_en")) : null)), h("tbody", {}, rows))),
  h("div", { class: "row", style: "margin-top:10px" }, btn, note));
}

export function render(root, data, ctx) {
  const out = outputsOf(data, "script");
  stepPage(root, "script", data, ctx, {
    early: () => [ownScript(ctx, data)],
    body: () => {
      const mode = lastInput(data, "script:mode")?.value;
      return [
        h("section", { class: "card" }, h("div", { class: "stack" },
          choiceInput(ctx, data, "script", "mode", t("step.script"), [["mine", t("script.mine")], ["write", t("script.write")]]),
          mode === "mine" || lastInput(data, "script:own_script") ? ownScript(ctx, data) : null)),
        scriptTable(ctx, data, out.script),
        ...outputTables(ctx, data, "script", { skip: ["script"] }),
      ];
    },
  });
}
