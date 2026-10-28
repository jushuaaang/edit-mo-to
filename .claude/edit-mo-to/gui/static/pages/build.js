// Build & QA (steps 7-8): build status, the qa_check / qa PASS / FAIL / OPEN table per timeline (outputs "qa…"),
// "Ask Claude to fix" on a FAIL (an action), the CapCut banner when a write is coming.
// Gate: project name taken (the `name` dialog, opened once per gate; it never overwrites).
import { h, chip } from "../ui.js";
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
  return h("div", { class: "banner wait" }, h("span", {}, String(q.text || "That project name is already taken in CapCut.")),
    sent ? chip(`Sent: ${String(sent.value)}`, "wait")
      : h("button", { class: "btn sm pri", type: "button", onclick: () => ctx.openDialog("name", args) }, "Choose another name"));
}

const STATE_TEXT = { working: "Claude is building", done: "Built and checked", error: "The build stopped with an error",
  waiting: "Waiting on you", skipped: "Skipped" };

export function render(root, data, ctx) {
  const out = outputsOf(data, "build");
  const qaKinds = Object.keys(out).filter((k) => k.startsWith("qa"));
  stepPage(root, "build", data, ctx, {
    hide: [NAME_Q],
    body: () => [
      nameBanner(ctx, data),
      h("section", { class: "card" }, h("h3", {}, "Build"),
        h("p", {}, STATE_TEXT[stateOf(data, "build")] || "Not started",
          card(data).project ? h("span", { class: "hint" }, " · project ", h("span", { class: "mono" }, String(card(data).project))) : null)),
      ...outputTables(ctx, data, "build", { only: (k) => qaKinds.includes(k), actions: (r, kind) => {
        if (r.status !== "err") return null;
        return actionButton(ctx, data, "build", `build:fix:${kind}:${r.id}`, "Ask Claude to fix", { value: () => ({ check: r.cells }) });
      } }),
      qaKinds.length ? null : h("section", { class: "card" }, h("h3", {}, "QA"), h("p", { class: "hint" }, "QA results per timeline show here after the build.")),
      ...outputTables(ctx, data, "build", { skip: qaKinds }),
    ],
  });
}
