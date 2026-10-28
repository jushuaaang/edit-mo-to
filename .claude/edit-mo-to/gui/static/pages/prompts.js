// B-roll & prompts (step 6): B-roll source, generator and (for a generator with models) the model as
// buttons (marked "already answered" when the storyboard step asked them: card.broll_source / card.generator), the
// prompts per timeline as rows with Copy and the full prompt on expand, and QA results. Gates: source; generator;
// generator_model. The generators and models come from generators.json (`data.generators`), never a list in this page.
import { h, helpTip } from "../ui.js";
import { t, label } from "../words.js";
import { stepPage, choiceInput, outputsOf, outputTables, isTable, card, promptText, copyButton, lastInput, gateAsks }
  from "../steppage.js";

const SOURCES = [["client", "Client's B-roll"], ["ai", "Generate AI video"], ["both", "Both"]];
const OTHER = "other";   // the gate's "Other" model: Claude asks its name and uses the safe limits (data.generators.safe)
const norm = (s) => String(s ?? "").trim().toLowerCase();

/** The card says e.g. "Client's B-roll"; match it to an option value. */
function cardValue(options, raw) {
  if (!raw) return undefined;
  const s = norm(raw);
  const hit = options.find(([v, label]) => s === v || s === label.toLowerCase() || s.includes(v));
  return hit ? hit[0] : String(raw);
}

function table(data) {
  const t = data?.generators;
  return t && typeof t.generators === "object" && t.generators ? t : null;
}

const labelled = (rows) => Object.entries(rows || {}).map(([k, v]) => [k, String(v?.label ?? k)]);
const find = (rows, s) => Object.entries(rows || {}).find(([k, v]) => s === norm(k) || s === norm(v?.label))?.[0];

/** A model by key, label, or a name without a version (the site's `aliases`: a family name -> its row). */
const findModel = (row, s) => find(row?.models, s) ?? (row?.aliases?.[s] in (row?.models || {}) ? row.aliases[s] : undefined);

/** The card says e.g. "<site> · <model label>", "<site>", "<model>" or an old job's alias name: {site, model} values. */
function fromCard(tbl, raw) {
  if (!raw) return {};
  const [head, ...rest] = String(raw).split("·").map(norm);
  const alias = tbl.aliases?.[head];
  if (alias) return { site: alias.generator, model: alias.model };
  const site = find(tbl.generators, head);
  if (!site) {  // a model name alone, without the site: the site whose models or aliases know it
    const hit = Object.keys(tbl.generators).find((k) => findModel(tbl.generators[k], head));
    return hit ? { site: hit, model: findModel(tbl.generators[hit], head) } : { site: String(raw) };
  }
  const tail = rest.join("·").trim();
  return { site, model: tail ? findModel(tbl.generators[site], tail) ?? OTHER : undefined };
}

function modelNote(tbl, row, model) {
  if (model === OTHER) {
    const safe = tbl.safe || {};
    return [safe.min_s, safe.max_s, safe.max_attach].every((x) => typeof x === "number")
      ? t("prompts.unknown_model", { min: safe.min_s, max: safe.max_s, attach: safe.max_attach }) : t("prompts.unknown_model_plain");
  }
  const m = row?.models?.[model];
  return m && m.verified == null ? t("prompts.unverified", { model: m.label ?? model }) : null;
}

function choices(ctx, data) {
  const c = card(data);
  const items = [choiceInput(ctx, data, "prompts", "broll_source", "B-roll source", SOURCES,
    { current: cardValue(SOURCES, c.broll_source), answeredNote: "already answered at the storyboard" })];
  const tbl = table(data);
  if (!tbl) return [...items, h("p", { class: "hint" }, t("prompts.no_table"))];
  const was = fromCard(tbl, c.generator);
  items.push(choiceInput(ctx, data, "prompts", "generator", "Generator", labelled(tbl.generators),
    { current: was.site, answeredNote: "already answered" }));
  const site = lastInput(data, "prompts:generator")?.value ?? was.site;
  const row = tbl.generators[site];
  if (row?.models || gateAsks(data, "prompts", "generator_model")) {
    const model = lastInput(data, "prompts:generator_model")?.value ?? was.model;
    const note = modelNote(tbl, row, model);
    items.push(choiceInput(ctx, data, "prompts", "generator_model", row?.label ? `${row.label} model` : "Model",
      [...labelled(row?.models), [OTHER, "Other"]], { current: was.model, answeredNote: "already answered" }));
    items.push(h("p", { class: "hint words" }, t("help.row"), h("span", { class: "word" }, t("word.model"), helpTip("model"))));
    if (note) items.push(h("p", { class: "hint" }, note));
  }
  return items;
}

/** A row: id and shot; the full prompt on expand and Copy, only when the row has a real prompt. */
function promptRow(r) {
  const text = promptText(r);
  const head = [h("b", {}, label(r.id)), " ", h("span", {}, (r.cells || []).slice(1).filter(Boolean).join(" · "))];
  return h("li", {},
    text ? h("details", {}, h("summary", {}, ...head), h("pre", { class: "prompt" }, text))
      : h("div", {}, ...head, h("div", { class: "hint" }, "No prompt to copy (a client clip, or Claude hasn't written it yet).")),
    text ? copyButton(text, "Copy") : null);
}

function promptCard(kind, tb) {
  return h("section", { class: "card" }, h("h3", {}, tb.title || kind, helpTip("prompt")),
    tb.rows.length ? h("ul", { class: "prompts" }, tb.rows.map(promptRow)) : h("p", { class: "hint" }, "No prompts yet."));
}

export function render(root, data, ctx) {
  const out = outputsOf(data, "prompts");
  const promptKinds = Object.keys(out).filter((k) => k.startsWith("prompts") && isTable(out[k]));
  stepPage(root, "prompts", data, ctx, {
    early: () => choices(ctx, data),
    body: () => [
      h("section", { class: "card" }, h("h3", {}, "B-roll", helpTip("b_roll")), h("div", { class: "stack" }, choices(ctx, data))),
      ...(promptKinds.length ? promptKinds.map((k) => promptCard(k, out[k]))
        : [h("section", { class: "card" }, h("h3", {}, "Prompts", helpTip("prompt")), h("p", { class: "hint" }, "Claude writes the prompts per timeline here."))]),
      ...outputTables(ctx, data, "prompts", { skip: promptKinds }),
    ],
  });
}
