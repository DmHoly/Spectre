"use strict";

/* Unit tests for what the step report reads from a process (spectre/plugins/step_report/static/
   report-core.js : stepRows, substrateRows, buildReport) - pure functions, the same for the builder's
   steps and a study's recorded ones. Run with:

     node --test
*/

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const filename = path.join(__dirname, "..", "spectre", "plugins", "step_report", "static", "report-core.js");
const { StepReportCore } = vm.runInThisContext(`${fs.readFileSync(filename, "utf8")}\n;({ StepReportCore })`, { filename });

const rows = (step, declared) => StepReportCore.stepRows(step, declared).map((r) => [r.label, r.value, r.declared]);

test("a deposition reads as its fields, in their order, with units", () => {
  const step = { id: "st_00000001", kind: "deposition", name: "Oxyde", material: "SiO2", recipe: "ALD Conformal", thickness: { value: 30, unit: "nm" }, description: null };
  assert.deepEqual(rows(step), [
    ["Matériau", "SiO2", false],
    ["Recette", "ALD Conformal", false],
    ["Épaisseur", "30 nm", false],
  ]);
  assert.deepEqual(rows({ kind: "etch", name: "G", depth: { value: 0.5, unit: "um" } }), [["Profondeur", "0.5 µm", false]]);
});

test("the declared parameters follow, marked, with their unit and what was said about how they were obtained", () => {
  const declared = [
    { name: "Dopage", value: 5, unit: "e17 cm-3", obtention: { precurseur: "SiH4" } },
    { name: "Flux", value: 12, obtention: { unit: "sccm" } },
  ];
  const all = StepReportCore.stepRows({ kind: "chemical", name: "N", description: "bain HF" }, declared);
  assert.deepEqual(
    all.map((r) => [r.label, r.value, r.declared]),
    [["Description", "bain HF", false], ["Dopage", "5 e17 cm-3", true], ["Flux", "12 sccm", true]]
  );
  assert.equal(all[1].detail, "precurseur : SiH4");
});

test("lithography: openings and their anchoring to the lattice; an unknown field shows under its own name", () => {
  const free = rows({ kind: "lithography", name: "L", resist_material: "Photoresist", thickness: { value: 500, unit: "nm" }, openings: [[80, 140], [300, 360]] });
  assert.deepEqual(free.at(-1), ["Ouvertures", "2 (80–140, 300–360 nm)", false]);
  const anchored = rows({ kind: "lithography", name: "L", openings: [[1, 2]], lattice_opening: { mode: "between", width: 120 } });
  assert.deepEqual(anchored.slice(-2), [["Ouvertures", "Entre les fils", false], ["Largeur entre les fils", "120 nm", false]]);
  assert.deepEqual(rows({ kind: "future_kind", name: "F", flux_ratio: 2 }), [["Flux ratio", "2", false]]);
  assert.deepEqual(rows({ kind: "epitaxial_growth", name: "E", orientation: "semi_polar", angle_deg: 30 }), [["Orientation", "Semi-polaire", false], ["Angle", "30 °", false]]);
  // l'angle n'a d'effet qu'en semi-polaire
  assert.deepEqual(rows({ kind: "epitaxial_growth", name: "E", orientation: "c_plane", angle_deg: 30 }), [["Orientation", "Plan C [0001]", false]]);
});

test("the substrate and its lattice", () => {
  const sub = StepReportCore.substrateRows({ material: "Si", domain_width: { value: 200, unit: "nm" }, thickness: { value: 50, unit: "nm" }, lattice: { pitch: 100, wires: 2 } });
  assert.deepEqual(
    sub.map((r) => [r.label, r.value]),
    [["Matériau", "Si"], ["Largeur du domaine", "200 nm"], ["Épaisseur", "50 nm"], ["Réseau de fils", "2 fils · pas 100 nm"]]
  );
});

test("a report is composed from the process, its simulated frames and the comments", () => {
  const frame = (materials, layers) => ({ svg: '<svg><path data-layer-index="0"/><path data-layer-index="1"/></svg>', materials, layers });
  const frames = [frame(["Si"], [{ step_index: -1 }]), frame(["Si", "SiO2"], [{ step_index: -1 }, { step_index: 0 }])];
  const input = {
    title: "Étude",
    subtitle: "µprojet X",
    logoSvg: "",
    substrate: { material: "Si", domain_width: { value: 200, unit: "nm" }, thickness: { value: 50, unit: "nm" } },
    steps: [{ step: { id: "st_00000001", kind: "deposition", name: "Oxyde", material: "SiO2", thickness: { value: 30, unit: "nm" }, brick_name: "SAG" }, declared: [] }],
    frames,
    colors: { Si: "#5b5f66", SiO2: "#8ecae6" },
    comments: { st_00000001: "Lent" },
  };
  const report = StepReportCore.buildReport(input);
  const [step] = report.steps;
  assert.deepEqual([step.kindLabel, step.color, step.summary, step.tags, step.comment], ["Dépôt", "#1d6fae", "SiO2 · 30 nm", ["Brique : SAG"], "Lent"]);
  assert.match(step.svg, /data-layer-index="1" class="sbr-new"/); // la couche de l'étape, et elle seule
  assert.doesNotMatch(step.svg, /data-layer-index="0" class/);
  assert.deepEqual(step.materials, [{ name: "Si", color: "#5b5f66" }, { name: "SiO2", color: "#8ecae6" }]);
  assert.deepEqual(report.cover.stats.map((s) => s.value), ["1", "2", "1"]);
  assert.equal(StepReportCore.buildReport({ ...input, comments: null }).cover.stats.length, 2); // pas de commentaires ici : pas de compteur
});

test("the file name is the title, simplified", () => {
  assert.equal(StepReportCore.fileName("Contact ohmique PGaN — dopage"), "rapport-Contact-ohmique-PGaN-dopage.html");
  assert.equal(StepReportCore.fileName("***"), "rapport-structure.html");
});
