// Script (step 3): "Use my script" or "Write one", the editable script table (with the "English (temporary)"
// column when TEMP_EN is on), Claude's script QA. "Storyboard first?" and script approval come from the gate.
// Cell edits are `edit` events (target "script:<line id>") and show "pending" until Claude applies them.
import { h, chip, pendingChip, toast } from "../ui.js";
import { stepPage, textInput, choiceInput, outputsOf, outputTables, pendingFor, sendEdit, lastInput, waitingText } from "../steppage.js";

const ownScript = (ctx, data) => textInput(ctx, data, "script", "own_script", "Your script", { rows: 8,
  placeholder: "Paste your script here, one line per row (hooks first, then the body).",
  hint: "Claude uses it as written and only checks it against the brief.", button: "Save my script" });

function scriptTable(ctx, data, script) {
  const lines = script?.lines || [];
  if (!lines.length) return h("section", { class: "card" }, h("h3", {}, "Script"), h("p", { class: "hint" }, "Claude's script shows here once it's written."));
  const temp = Boolean(script.temp_en);
  const cells = new Map();
  const rows = lines.map((ln) => {
    const id = String(ln.id ?? "");
    const pend = pendingFor(data, `script:${id}`).pop();
    const text = pend && typeof pend.value === "string" ? pend.value : String(ln.text ?? "");
    const ta = h("textarea", { class: "f cell", rows: "2", "data-key": `script:${id}`, "aria-label": `Line ${id}` }, text);
    cells.set(id, ta);
    return h("tr", { "data-id": id }, h("td", { class: "mono" }, id, pend ? h("div", {}, pendingChip()) : null), h("td", {}, ta),
      temp ? h("td", { class: "hint" }, String(ln.en ?? "")) : null);
  });
  const note = h("span", { class: "hint", role: "status" });
  const btn = h("button", { class: "btn pri", type: "button" }, "Send edits");
  btn.addEventListener("click", async () => {
    const changed = [...cells].filter(([, ta]) => ta.value.trim() && ta.value !== ta.defaultValue);
    if (!changed.length) { note.textContent = "Nothing changed."; return; }
    btn.disabled = true;
    try {
      for (const [id, ta] of changed) await sendEdit(ctx, "script", `script:${id}`, ta.value.trim());
      note.textContent = waitingText(data);
    } catch (e) {
      toast(e.message || "Not sent. Try again.");
    } finally {
      btn.disabled = false;
    }
  });
  return h("section", { class: "card" }, h("div", { class: "row spread" }, h("h3", {}, "Script"),
    h("div", { class: "row" }, chip(`Language: ${script.lang || "?"}`, "mute"), temp ? chip("TEMP_EN on · delete before export", "err") : null)),
  h("div", { class: "tablewrap" }, h("table", {}, h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Id"),
    h("th", { scope: "col" }, "Line"), temp ? h("th", { scope: "col" }, "English (temporary)") : null)), h("tbody", {}, rows))),
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
          choiceInput(ctx, data, "script", "mode", "Script", [["mine", "Use my script"], ["write", "Write one"]]),
          mode === "mine" || lastInput(data, "script:own_script") ? ownScript(ctx, data) : null)),
        scriptTable(ctx, data, out.script),
        ...outputTables(ctx, data, "script", { skip: ["script"] }),
      ];
    },
  });
}
