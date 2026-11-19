// Build & QA (steps 7-8): build status, the qa_check / qa PASS / FAIL / OPEN table per timeline (outputs "qa…"),
// "Ask Claude to fix" on a FAIL (an action), the CapCut banner when a write is coming.
// Gate: project name taken (the `name` dialog, opened once per gate; it never overwrites).
import { h, chip } from "../ui.js";
import { t } from "../words.js";
import { stepPage, outputsOf, outputTables, actionButton, openGate, stateOf, card, gateAnswer } from "../steppage.js";

const NAME_Q = "project_name";
const opened = new Set();  // gate ids whose name dialog was shown once already

function nameBanner(ctx, data) {
  const gate = openGate(data, "build");
  const q = gate?.questions?.find((x) => x.id === NAME_Q);
  if (!q) return null;
  const args = { gate, q, product: card(data).product };
  if (!gateAnswer(data, gate, q.id) && !opened.has(gate.id)) {
    opened.add(gate.id);
    setTimeout(() => ctx.openDialog("name", args), 0);
  }
  const sent = gateAnswer(data, gate, q.id);
  return h("div", { class: "banner wait" }, h("span", {}, String(q.text || t("build.name_taken"))),
    sent ? chip(t("build.sent", { value: String(sent.value) }), "wait")
      : h("button", { class: "btn sm pri", type: "button", onclick: () => ctx.openDialog("name", args) }, t("build.choose")));
}

const STATE_TEXT = { working: "build.st_working", done: "build.st_done", error: "build.st_error", waiting: "build.st_waiting",
  skipped: "build.st_skipped" };

export function render(root, data, ctx) {
  const out = outputsOf(data, "build");
  const qaKinds = Object.keys(out).filter((k) => k.startsWith("qa"));
  stepPage(root, "build", data, ctx, {
    hide: [NAME_Q],
    body: () => [
      nameBanner(ctx, data),
      h("section", { class: "card" }, h("h3", {}, t("build.h")),
        h("p", {}, t(STATE_TEXT[stateOf(data, "build")] || "sp.not_started"),
          card(data).project ? h("span", { class: "hint" }, ` · ${t("build.project")} `, h("span", { class: "mono" }, String(card(data).project))) : null)),
      ...outputTables(ctx, data, "build", { only: (k) => qaKinds.includes(k), actions: (r, kind) => {
        if (r.status !== "err") return null;
        return actionButton(ctx, data, "build", `build:fix:${kind}:${r.id}`, t("build.fix"), { value: () => ({ check: r.cells }) });
      } }),
      qaKinds.length ? null : h("section", { class: "card" }, h("h3", {}, t("build.qa_h")), h("p", { class: "hint" }, t("build.qa_empty"))),
      ...outputTables(ctx, data, "build", { skip: qaKinds }),
    ],
  });
}
