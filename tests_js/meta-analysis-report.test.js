"use strict";

/* Unit tests for the report of a wafer analysis (spectre/plugins/meta_analysis/static/report-html.js :
   AnalysisReport.build, AnalysisReport.differences) - pure functions from the page's data to one self-contained
   HTML page. Run with:

     node --test
*/

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const filename = path.join(__dirname, "..", "spectre", "plugins", "meta_analysis", "static", "report-html.js");
const { AnalysisReport } = vm.runInThisContext(`${fs.readFileSync(filename, "utf8")}\n;({ AnalysisReport })`, { filename });

const SVG = '<svg viewBox="0 0 10 10"><rect width="10" height="10" fill="#8ecae6"/></svg>';

function report(overrides = {}) {
  return {
    title: "Pourquoi <B12> brille",
    question: "EQE + 30 % & pourquoi ?",
    conclusion: "Le recuit.\nÀ vérifier sur <deux> plaques.",
    date: "17 octobre 2026",
    byline: "Créée par Ada le 17 octobre 2026",
    logoSvg: '<svg viewBox="0 0 4 4"></svg>',
    wafers: [
      { lasermark: "W-REF", color: "var(--navy)", isRef: true, structure: { svg: SVG, caption: "Vue dans Essai" }, facts: [{ label: "Lot", value: "QML11" }], notes: { context: "Plaque témoin", hypothesis: null, learnings: "Stable" }, studies: [{ title: "Essai", status: "Conclue", conclusion: "Concluant", next: "Répliquer" }] },
      { lasermark: "B12", color: "var(--viz-1)", isRef: false, structure: null, facts: [], notes: null, studies: [] },
    ],
    differences: [{ lasermark: "B12", color: "var(--viz-1)", comparable: true, items: [{ kind: "changed", step: "Oxyde", parameter: "Épaisseur", from: "20 nm", to: "35 nm" }], kpis: [{ title: "EQE max", text: "▲ +0,003 (+14 %)", verdict: "better" }] }],
    kpis: [{ title: "EQE max", source: "EQE · %", better: "high", status: "ok", message: "", svg: SVG, rows: [{ lasermark: "W-REF", color: "var(--navy)", isRef: true, n: "109", median: "0,021", delta: "référence", verdict: "", date: "—" }] }],
    sheets: [{ title: "PL", kind: "Cartographie", figure: SVG }],
    ...overrides,
  };
}

test("the report is one self-contained page that escapes every text", () => {
  const html = AnalysisReport.build(report());
  assert.match(html, /^<!doctype html>/);
  assert.ok(!/<script|<link|src="http/i.test(html), "nothing to load: no script, no stylesheet, no remote image");
  assert.ok(html.includes("Pourquoi &lt;B12&gt; brille") && !html.includes("<B12>"));
  assert.ok(html.includes("EQE + 30 % &amp; pourquoi ?"));
  assert.ok(html.includes("À vérifier sur &lt;deux&gt; plaques.") && html.includes("Le recuit.<br>"));
  assert.ok(html.includes('class="top__logo"'), "the logo is embedded");
});

test("the report has the wafers, what differs and moves, the KPIs, the data sheet, the context and the conclusion", () => {
  const html = AnalysisReport.build(report());
  for (const title of ["Les plaques côte à côte", "Ce qui diffère de la référence, ce qui bouge", "KPI face à la référence", "Fiche data des plaques", "Contexte et enseignements de chaque plaque", "Ce qu'on a compris"]) {
    assert.ok(html.includes(title), title);
  }
  assert.ok(html.includes("<span class=\"mono\">20 nm</span> → <span class=\"mono\">35 nm</span>"));
  assert.ok(html.includes("▲ +0,003 (+14 %) · mieux"), "the verdict is written, not only colored");
  assert.ok(html.includes("Plaque témoin") && html.includes("Répliquer"));
  assert.ok(html.includes("Pas de structure dessinée"), "a wafer without a structure keeps its place");
});

test("empty parts are left out, and a missing conclusion is said", () => {
  const html = AnalysisReport.build(report({ differences: [], kpis: [], sheets: [], conclusion: "", wafers: [report().wafers[1]] }));
  assert.ok(!html.includes("KPI face à la référence") && !html.includes("Fiche data des plaques") && !html.includes("ce qui bouge"));
  assert.ok(!html.includes("Contexte et enseignements"), "no notes, no studies: no context section");
  assert.ok(html.includes("Pas encore de conclusion."));
});

test("a color only enters a style attribute when it is a color", () => {
  const html = AnalysisReport.build(report({ wafers: [{ ...report().wafers[0], color: "red;background:url(x)" }] }));
  assert.ok(!html.includes("url(x)"));
});

test("differences lists what a row of the comparator changes from its base, as the server does", () => {
  const result = {
    baseline: 0,
    groups: [
      { label: "Oxyde", columns: [{ label: "Épaisseur" }, { label: "Dopage" }] },
      { label: "Contact", columns: [{ label: "Épaisseur" }] },
      { label: "Gravure", columns: [{ label: "Profondeur" }] },
    ],
    rows: [
      { cells: [{ status: "same", text: "20 nm" }, { status: "empty", text: "" }, { status: "absent", text: "—" }, { status: "same", text: "10 nm" }] },
      { cells: [{ status: "changed", text: "35 nm" }, { status: "added_param", text: "5e17" }, { status: "added_layer", text: "50 nm" }, { status: "moved", text: "10 nm", changed: false }] },
      { cells: null },
    ],
  };
  assert.deepEqual(AnalysisReport.differences(result, 1), [
    { kind: "changed", step: "Oxyde", parameter: "Épaisseur", from: "20 nm", to: "35 nm" },
    { kind: "added_param", step: "Oxyde", parameter: "Dopage", from: null, to: "5e17" },
    { kind: "added_layer", step: "Contact", parameter: null, from: null, to: null },
    { kind: "moved", step: "Gravure", parameter: null, from: null, to: null },
  ]);
  assert.deepEqual(AnalysisReport.differences(result, 0), [], "the base differs from nothing");
  assert.deepEqual(AnalysisReport.differences(result, 2), [], "a row without cells has nothing to compare");
});
