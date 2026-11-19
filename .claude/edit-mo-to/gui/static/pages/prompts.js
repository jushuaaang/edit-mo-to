// B-roll & prompts (step 6): B-roll source, generator and (for a generator with models) the model as
// buttons (marked "already answered" when the storyboard step asked them: card.broll_source / card.generator), the
// prompts per timeline as rows with Copy and the full prompt on expand, and QA results. Gates: source; generator;
// generator_model. The generators and models come from generators.json (`data.generators`), never a list in this page;
// `data.generators.picks` (the server's generators.pick_model over this computer's prefs) is the model Claude would
// pick, highlighted while nothing is chosen. Every model stays choosable. Each prompt row has "Got flagged".
import { h, helpTip } from "../ui.js";
import { t, tEn, label } from "../words.js";
import { stepPage, choiceInput, outputsOf, outputTables, isTable, card, promptText, copyButton, lastInput, gateAsks,
  flaggedBox } from "../steppage.js";

const SOURCES = [["client", "prompts.src_client"], ["ai", "prompts.src_ai"], ["both", "prompts.src_both"]];  // value, word
const OTHER = "other";   // the gate's "Other" model: Claude asks its name and uses the safe limits (data.generators.safe)
const norm = (s) => String(s ?? "").trim().toLowerCase();

/** The card says e.g. "Client's B-roll" (Claude writes it in English); match it to an option value. */
function cardValue(options, raw) {
  if (!raw) return undefined;
  const s = norm(raw);
  const hit = options.find(([v, key]) => s === v || s === tEn(key).toLowerCase() || s.includes(v));
  return hit ? hit[0] : String(raw);
}

function table(data) {
  const g = data?.generators;
  return g && typeof g.generators === "object" && g.generators ? g : null;
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

/** The job's site (a generators.json key) from the card's generator, or null when none is chosen yet. A name the
 *  table doesn't know comes back as written; no table: the card text as written. */
export function siteOf(data) {
  const raw = card(data).generator;
  if (!raw) return null;
  const tbl = table(data);
  return tbl ? fromCard(tbl, raw).site ?? String(raw) : String(raw);
}

function modelNote(tbl, row, model) {
  if (model === OTHER) {
    // a site with limits of its own keeps them for an unknown model; the others use the table's safe limits
    const own = [row?.min_s, row?.max_s, row?.max_attach].every((x) => typeof x === "number");
    const safe = own ? row : tbl.safe || {};
    return [safe.min_s, safe.max_s, safe.max_attach].every((x) => typeof x === "number")
      ? t("prompts.unknown_model", { min: safe.min_s, max: safe.max_s, attach: safe.max_attach }) : t("prompts.unknown_model_plain");
  }
  const m = row?.models?.[model];
  return m && m.verified == null ? t("prompts.unverified", { model: m.label ?? model }) : null;
}

function choices(ctx, data) {
  const c = card(data);
  const items = [choiceInput(ctx, data, "prompts", "broll_source", t("prompts.broll_source"), SOURCES.map(([v, k]) => [v, t(k)]),
    { current: cardValue(SOURCES, c.broll_source), answeredNote: t("prompts.answered_storyboard") })];
  const tbl = table(data);
  if (!tbl) return [...items, h("p", { class: "hint" }, t("prompts.no_table"))];
  const was = fromCard(tbl, c.generator);
  const picks = tbl.picks && typeof tbl.picks === "object" ? tbl.picks : {};
  const pickSite = typeof picks.default === "string" ? picks.default.split(":")[0] : undefined;
  items.push(choiceInput(ctx, data, "prompts", "generator", t("prompts.generator"), labelled(tbl.generators),
    { current: was.site, answeredNote: t("sp.already_answered"), suggested: pickSite }));
  const site = lastInput(data, "prompts:generator")?.value ?? was.site;
  const row = tbl.generators[site];
  // a model answer belongs to the site that was chosen when it was given; after the site changes it no longer counts
  const siteAt = (seq) => [...(data?.events || [])].filter((e) => e.type === "answer" && e.target === "prompts:generator" && !e.stale && e.seq < seq)
    .pop()?.value ?? was.site;
  const stale = (e) => siteAt(e.seq) !== site;
  const asked = lastInput(data, "prompts:generator_model");
  const kept = asked && !stale(asked) ? asked.value : undefined;
  if (row?.models || gateAsks(data, "prompts", "generator_model")) {
    const model = kept ?? (site === was.site ? was.model : undefined);
    const note = modelNote(tbl, row, model);
    const suggested = picks[site] ?? undefined;   // Claude's default for this site (never a model this editor avoids)
    const sugName = suggested ? String(row?.models?.[suggested]?.label ?? suggested) : "";
    items.push(choiceInput(ctx, data, "prompts", "generator_model", row?.label ? t("prompts.site_model", { site: row.label }) : t("prompts.model"),
      [...labelled(row?.models), [OTHER, t("prompts.other")]], { current: model, ignore: stale, answeredNote: t("sp.already_answered"),
        suggested, suggestedNote: suggested ? t("prompts.default_hint", { model: sugName }) : null }));
    items.push(h("p", { class: "hint words" }, t("help.row"), h("span", { class: "word" }, t("word.model"), helpTip("model"))));
    if (note) items.push(h("p", { class: "hint" }, note));
  }
  return items;
}

/** A row: id and shot; the full prompt on expand, Copy and "Got flagged", only when the row has a real prompt. The
 *  row's note (Claude's, e.g. "rewritten after a flag") shows under it. */
function promptRow(ctx, data, r) {
  const text = promptText(r);
  const head = [h("b", {}, label(r.id)), " ", h("span", {}, (r.cells || []).slice(1).filter(Boolean).join(" · "))];
  return h("li", {},
    h("div", {}, text ? h("details", {}, h("summary", {}, ...head), h("pre", { class: "prompt" }, text))
      : h("div", {}, ...head, h("div", { class: "hint" }, t("prompts.no_prompt"))),
    typeof r.note === "string" && r.note ? h("div", { class: "hint" }, r.note) : null),
    text ? h("div", { class: "prompt-acts" }, copyButton(text, t("common.copy")), flaggedBox(ctx, data, "prompts", String(r.id))) : null);
}

function promptCard(ctx, data, kind, tb) {
  return h("section", { class: "card" }, h("h3", {}, tb.title || kind, helpTip("prompt")),
    tb.rows.length ? h("ul", { class: "prompts" }, tb.rows.map((r) => promptRow(ctx, data, r))) : h("p", { class: "hint" }, t("prompts.none_yet")));
}

export function render(root, data, ctx) {
  const out = outputsOf(data, "prompts");
  const promptKinds = Object.keys(out).filter((k) => k.startsWith("prompts") && isTable(out[k]));
  stepPage(root, "prompts", data, ctx, {
    early: () => choices(ctx, data),
    body: () => [
      h("section", { class: "card" }, h("h3", {}, t("prompts.broll_h"), helpTip("b_roll")), h("div", { class: "stack" }, choices(ctx, data))),
      ...(promptKinds.length ? promptKinds.map((k) => promptCard(ctx, data, k, out[k]))
        : [h("section", { class: "card" }, h("h3", {}, t("prompts.prompts_h"), helpTip("prompt")), h("p", { class: "hint" }, t("prompts.empty_p")))]),
      ...outputTables(ctx, data, "prompts", { skip: promptKinds }),
    ],
  });
}
