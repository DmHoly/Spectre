"use strict";

/* Unit tests for the drawings of a wafer's data sheet (spectre/plugins/wafer_data/static/charts.js): pure
   functions that return an SVG string from the digests the server computes (wafer_data/digest.py). Run with:

     node --test tests_js/*.test.js
*/

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

globalThis.escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const filename = path.join(__dirname, "..", "spectre", "plugins", "wafer_data", "static", "charts.js");
const { WaferDataCharts: C } = vm.runInThisContext(`${fs.readFileSync(filename, "utf8")}\n;({ WaferDataCharts })`, { filename });

const count = (svg, needle) => svg.split(needle).length - 1;
const clean = (svg) => assert.ok(!/NaN|undefined|Infinity/.test(svg), svg.match(/.{40}(NaN|undefined|Infinity).{20}/)?.[0]);

const envelope = (shift) => ({ x: [1, 2, 3, 4], median: [1 + shift, 2 + shift, 3 + shift, 4 + shift], low: [0.5, 1, 2, 3], high: [2, 3, 4, 5 + shift] });

test("curves coloured by a category draw one band and one median per group, with a legend", () => {
  const d = { n: 9, log_x: false, log_y: true, ...envelope(0), groups: ["600", "800", "Autres"], series: [{ label: "600", n: 3, ...envelope(0) }, { label: "Autres", n: 6, ...envelope(1) }] };
  const svg = C.curve(d, "", { xLabel: "V (V)", yLabel: "EQE" });
  clean(svg);
  assert.equal(count(svg, 'class="wd-band"'), 2);
  assert.equal(count(svg, 'class="wd-line"'), 2);
  assert.ok(svg.includes("var(--viz-8)"), "« Autres » est gris");
  assert.ok(svg.includes("V (V)") && svg.includes("EQE"));
  const keys = C.legend(d.groups, C.groupColors(d.groups), "pitch_nm");
  assert.equal(count(keys, "wd-keys__item"), 3);
});

test("each curve is drawn in its group colour, with the overall median", () => {
  const d = { n: 50, log_x: true, log_y: false, ...envelope(0), groups: ["a", "b"], curves: [{ g: 0, x: [1e-6, 1e-4, 1e-2], y: [0, 1, 2] }, { g: 1, x: [1e-6, 1e-3], y: [1, 3] }] };
  const svg = C.curve(d, "");
  clean(svg);
  assert.equal(count(svg, 'class="wd-trace"'), 2);
  assert.ok(svg.includes("wd-line--overall") && svg.includes("var(--viz-2)"));
});

test("a single curve takes the chosen palette colour", () => {
  const svg = C.curve({ n: 4, log_x: false, log_y: false, ...envelope(0) }, "", { color: 4 });
  clean(svg);
  assert.ok(svg.includes("var(--viz-4)"));
});

test("boxes, a scatter and a stacked histogram render without holes", () => {
  const box = (label, m) => ({ label, n: 10, minimum: m - 3, maximum: m + 3, whisker_low: m - 2, q1: m - 1, median: m, q3: m + 1, whisker_high: m + 2, mean: m, outliers: [m + 3] });
  const boxes = C.boxplot({ n: 20, log_y: false, boxes: [box("600", 5), box("800", 7)] }, "nm");
  clean(boxes);
  assert.equal(count(boxes, 'class="wd-box"'), 2);
  const one = C.boxplot({ n: 10, log_y: true, boxes: [box("", 5)] }, "", { color: 3 });
  clean(one);
  assert.ok(one.includes("var(--viz-3)"));

  const scatter = C.scatter({ n: 3, shown: 3, log_x: false, log_y: false, points: [[1, 2, 0], [2, 3, 1], [3, 1, 1]], groups: ["faux", "vrai"] }, { xLabel: "J", yLabel: "EQE" });
  clean(scatter);
  assert.equal(count(scatter, 'class="wd-dot"'), 3);

  const hist = C.histogram({ n: 6, minimum: 0, maximum: 3, median: 1, counts: [3, 0, 3], groups: ["a", "b"], series: [[2, 0, 1], [1, 0, 2]] }, "");
  clean(hist);
  assert.equal(count(hist, 'class="wd-bar"'), 4);
});
