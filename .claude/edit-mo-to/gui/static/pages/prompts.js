// B-roll & prompts (step 6): B-roll source and generator as buttons (marked "already answered" when the storyboard
// step asked them, card.broll_source / card.generator), the prompts per timeline as rows with Copy and the full prompt
// on expand, and QA results. Gates: source; generator.
import { h } from "../ui.js";
import { stepPage, choiceInput, outputsOf, outputTables, isTable, card, promptText, copyButton } from "../steppage.js";

const SOURCES = [["client", "Client's B-roll"], ["ai", "Generate AI video"], ["both", "Both"]];
const GENERATORS = [["seedance", "Seedance"], ["flow", "Google Flow"]];

/** The card says e.g. "Seedance"; match it to an option value. */
function cardValue(options, raw) {
  if (!raw) return undefined;
  const s = String(raw).toLowerCase();
  const hit = options.find(([v, label]) => s === v || s === label.toLowerCase() || s.includes(v));
  return hit ? hit[0] : String(raw);
}

function choices(ctx, data) {
  const c = card(data);
  return [
    choiceInput(ctx, data, "prompts", "broll_source", "B-roll source", SOURCES,
      { current: cardValue(SOURCES, c.broll_source), answeredNote: "already answered at the storyboard" }),
    choiceInput(ctx, data, "prompts", "generator", "Generator", GENERATORS,
      { current: cardValue(GENERATORS, c.generator), answeredNote: "already answered" }),
  ];
}

function promptCard(kind, t) {
  return h("section", { class: "card" }, h("h3", {}, t.title || kind),
    t.rows.length ? h("ul", { class: "prompts" }, t.rows.map((r) => h("li", {},
      h("details", {}, h("summary", {}, h("span", { class: "mono" }, String(r.id ?? "")), " ",
        h("span", {}, (r.cells || []).slice(1).filter(Boolean).join(" · "))),
      h("pre", { class: "prompt" }, promptText(r))),
      copyButton(promptText(r), "Copy")))) : h("p", { class: "hint" }, "No prompts yet."));
}

export function render(root, data, ctx) {
  const out = outputsOf(data, "prompts");
  const promptKinds = Object.keys(out).filter((k) => k.startsWith("prompts") && isTable(out[k]));
  stepPage(root, "prompts", data, ctx, {
    early: () => choices(ctx, data),
    body: () => [
      h("section", { class: "card" }, h("h3", {}, "B-roll"), h("div", { class: "stack" }, choices(ctx, data))),
      ...(promptKinds.length ? promptKinds.map((k) => promptCard(k, out[k]))
        : [h("section", { class: "card" }, h("h3", {}, "Prompts"), h("p", { class: "hint" }, "Claude writes the prompts per timeline here."))]),
      ...outputTables(ctx, data, "prompts", { skip: promptKinds }),
    ],
  });
}
