"use strict";

/* Unit tests for the step report's document (spectre/plugins/step_report/static/report-html.js :
   StepReportHtml.build) - a pure function from the report's data to one self-contained HTML page.
   Run with:

     node --test
*/

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const filename = path.join(__dirname, "..", "spectre", "plugins", "step_report", "static", "report-html.js");
const { StepReportHtml } = vm.runInThisContext(`${fs.readFileSync(filename, "utf8")}\n;({ StepReportHtml })`, { filename });

const SVG = '<svg viewBox="0 0 10 10"><path data-layer-index="0" class="sbr-new" fill="#8ecae6"/></svg>';

function report(overrides = {}) {
  return {
    title: "Contact <PGaN> & co",
    subtitle: "µprojet demo",
    date: "14 octobre 2026",
    cover: { svg: SVG, materials: [{ name: "Si", color: "#5b5f66" }], stats: [{ label: "étapes", value: "2" }] },
    start: { svg: SVG, materials: [{ name: "Si", color: "#5b5f66" }], params: [{ label: "Matériau", value: "Si", declared: false }] },
    steps: [
      {
        index: 1, kind: "deposition", kindLabel: "Dépôt", color: "#1d6fae", tint: "#e8f1fa", name: "Oxyde", summary: "SiO2 · 20 nm",
        tags: ["Brique : SAG"], svg: SVG, materials: [{ name: "SiO2", color: "#8ecae6" }],
        params: [
          { label: "Épaisseur", value: "20 nm", declared: false },
          { label: "Dopage", value: "5e17 cm⁻³", declared: true, detail: "précurseur : SiH4" },
        ],
        comment: "Dépôt lent <b>à vérifier</b>\nsur deux plaques",
      },
      { index: 2, kind: "etch", kindLabel: "Gravure", color: "#a45a3a", tint: "#f6ede7", name: "Gravure", summary: "", tags: [], svg: SVG, materials: [], params: [], comment: "" },
    ],
    ...overrides,
  };
}

test("the report is one self-contained page: a slide per step plus the title and the substrate, and a stepper chip each", () => {
  const html = StepReportHtml.build(report());
  assert.equal((html.match(/<section class="slide/g) || []).length, 4);
  assert.equal((html.match(/<button type="button" class="chip/g) || []).length, 4);
  assert.match(html, /^<!doctype html>/);
  assert.doesNotMatch(html, /<link |src="http|@import|url\(http/); // rien à charger
});

test("each slide carries the parameters (declared ones marked), the comment and the colour code", () => {
  const html = StepReportHtml.build(report());
  assert.match(html, /<th scope="row">Épaisseur<\/th><td>20 nm<\/td>/);
  assert.match(html, /Dopage<\/th><td>5e17 cm⁻³<span class="badge">déclaré<\/span><small>précurseur : SiH4<\/small>/);
  assert.match(html, /Brique : SAG/);
  assert.match(html, /<span class="legend__swatch" style="background:#8ecae6"><\/span>SiO2/);
  assert.equal((html.match(/aria-label="Code couleur"/g) || []).length, 4);
  assert.match(html, /Pas de commentaire sur cette étape/); // l'étape 2
  assert.equal((html.match(/chip has-comment/g) || []).length, 1);
});

test("everything the user typed is escaped", () => {
  const html = StepReportHtml.build(report());
  assert.doesNotMatch(html, /<b>à vérifier<\/b>/);
  assert.match(html, /Dépôt lent &lt;b&gt;à vérifier&lt;\/b&gt;\nsur deux plaques/);
  assert.match(html, /Contact &lt;PGaN&gt; &amp; co/);
});

test("a colour is never free CSS", () => {
  const evil = report();
  evil.steps[0].color = "red;background:url(http://x)";
  evil.steps[0].materials = [{ name: "X", color: '"><script>alert(1)</script>' }];
  const html = StepReportHtml.build(evil);
  assert.doesNotMatch(html, /url\(http/);
  assert.doesNotMatch(html, /<script>alert/);
});

test("the substrate slide has no comment block: it is not a step", () => {
  const html = StepReportHtml.build(report());
  const start = html.split('<section class="slide')[2];
  assert.doesNotMatch(start, /comment/);
});

test("the header carries the Aledia logo (inline) and Spectre; without a logo it still renders", () => {
  const html = StepReportHtml.build(report({ logoSvg: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><path d="M0 0"/></svg>' }));
  assert.match(html, /<div class="top__brand"><svg class="top__logo" xmlns=/);
  assert.match(html, /<span class="top__name">Spectre<\/span>/);
  const none = StepReportHtml.build(report({ logoSvg: "<img src=x onerror=alert(1)>" }));
  assert.match(none, /<div class="top__brand"><span class="top__name">/);
  assert.doesNotMatch(none, /onerror/);
});
