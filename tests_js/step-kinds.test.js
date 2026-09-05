"use strict";

/* Unit tests for the structure-builder step-kind registry (spectre/api/static/js/structure-builder/
   step-kinds.js) and the small pure helpers it depends on - the part of the modularization that
   replaced nine scattered per-kind branches with one entry per step kind. Run with:

     node --test

   No external dependency: Node's built-in test runner loads the real production files as-is (see
   helpers/load-structure-builder.js) - not a reimplementation, the actual shipped source. */

const test = require("node:test");
const assert = require("node:assert/strict");
const { loadStructureBuilder } = require("./helpers/load-structure-builder");

const { STEP_KIND_DEFS, STEP_KINDS, CAMPAIGN_FIELD_OPTIONS, PY_STEP_CLASS, stepSummary, pyStepCode, modeSummary, parseOpenings, pyStr, pyLength, pyDict, toNm } =
  loadStructureBuilder(
    ["form-widgets.js", "code-export.js", "step-kinds.js"],
    [
      "STEP_KIND_DEFS",
      "STEP_KINDS",
      "CAMPAIGN_FIELD_OPTIONS",
      "PY_STEP_CLASS",
      "stepSummary",
      "pyStepCode",
      "modeSummary",
      "parseOpenings",
      "pyStr",
      "pyLength",
      "pyDict",
      "toNm",
    ]
  );

test("modeSummary formats a mode with an optional angle suffix", () => {
  assert.equal(modeSummary("conformal", 0), "conforme");
  assert.equal(modeSummary("directional", 15), "directionnel (15°)");
  assert.equal(modeSummary("isotropic", 0), "isotrope");
});

test("parseOpenings turns 'a-b, c-d' text into pairs of numbers", () => {
  assert.deepEqual(parseOpenings(""), []);
  assert.deepEqual(parseOpenings("   "), []);
  assert.deepEqual(parseOpenings("20-40"), [[20, 40]]);
  assert.deepEqual(parseOpenings("20-40, 100-140"), [
    [20, 40],
    [100, 140],
  ]);
});

test("pyStr/pyLength/pyDict/toNm render Python literals", () => {
  assert.equal(pyStr("Dépôt"), '"Dépôt"');
  assert.equal(pyStr('a"b'), '"a\\"b"');
  assert.equal(pyLength({ value: 20, unit: "nm" }), 'Length(value=20, unit="nm")');
  assert.equal(pyDict({}), "{}");
  assert.equal(pyDict({ Si: 0.1 }), '{"Si": 0.1}');
  assert.equal(toNm({ value: 2, unit: "um" }), 2000);
  assert.equal(toNm({ value: 5, unit: "nm" }), 5);
});

test("STEP_KIND_DEFS registers exactly the nine known step kinds", () => {
  const kinds = Object.keys(STEP_KIND_DEFS).sort();
  assert.deepEqual(kinds, [
    "chemical",
    "deposition",
    "epitaxial_growth",
    "etch",
    "faceted_growth",
    "flip",
    "lithography",
    "planarization",
    "resist_strip",
  ]);
});

test("every step kind exposes the full contract renderKindFields/buildStepFromForm/stepSummary/pyStepCode rely on", () => {
  for (const [kind, def] of Object.entries(STEP_KIND_DEFS)) {
    assert.equal(typeof def.label, "string", `${kind}.label`);
    assert.equal(typeof def.color, "string", `${kind}.color`);
    assert.equal(typeof def.tint, "string", `${kind}.tint`);
    assert.equal(typeof def.iconPath, "string", `${kind}.iconPath`);
    assert.equal(typeof def.pyClass, "string", `${kind}.pyClass`);
    assert.equal(typeof def.renderFields, "function", `${kind}.renderFields`);
    assert.equal(typeof def.buildFromForm, "function", `${kind}.buildFromForm`);
    assert.equal(typeof def.summary, "function", `${kind}.summary`);
    assert.equal(typeof def.pyCode, "function", `${kind}.pyCode`);
    assert.ok(Array.isArray(def.campaignFields), `${kind}.campaignFields`);
  }
});

test("STEP_KINDS/CAMPAIGN_FIELD_OPTIONS/PY_STEP_CLASS are derived for every kind in the registry", () => {
  const kinds = Object.keys(STEP_KIND_DEFS).sort();
  assert.deepEqual(Object.keys(STEP_KINDS).sort(), kinds);
  assert.deepEqual(Object.keys(CAMPAIGN_FIELD_OPTIONS).sort(), kinds);
  assert.deepEqual(Object.keys(PY_STEP_CLASS).sort(), kinds);
  assert.equal(STEP_KINDS.deposition.label, "Dépôt");
  assert.equal(PY_STEP_CLASS.flip, "Flip");
  assert.deepEqual(CAMPAIGN_FIELD_OPTIONS.deposition, [["thickness", "Épaisseur"]]);
  assert.deepEqual(CAMPAIGN_FIELD_OPTIONS.chemical, []);
});

// One representative step per kind, in exactly the shape buildStepFromForm() produces - used to
// lock in both stepSummary() and pyStepCode() for every kind in one place.
const SAMPLE_STEPS = {
  deposition: { kind: "deposition", name: "Dépôt", material: "Si", recipe: "ALD Conformal", thickness: { value: 20, unit: "nm" } },
  etch: { kind: "etch", name: "Gravure", recipe: "Anisotropic RIE", depth: { value: 10, unit: "nm" } },
  planarization: { kind: "planarization", name: "Planarisation", target_level: { value: 0, unit: "nm" } },
  lithography: {
    kind: "lithography",
    name: "Lithographie",
    resist_material: "Photoresist",
    thickness: { value: 500, unit: "nm" },
    openings: [[20, 40]],
  },
  chemical: { kind: "chemical", name: "Nettoyage", description: null },
  resist_strip: { kind: "resist_strip", name: "Retrait de résine", material: "Photoresist" },
  faceted_growth: {
    kind: "faceted_growth",
    name: "Croissance facettée",
    material: "GaN",
    thickness: { value: 10, unit: "nm" },
    rate_c: 1,
    rate_m: 0.4,
    rate_sp: 0.15,
    semi_polar_angle_deg: 30,
    seed_materials: ["GaN"],
  },
  epitaxial_growth: {
    kind: "epitaxial_growth",
    name: "Croissance épitaxiale",
    material: "GaN",
    thickness: { value: 20, unit: "nm" },
    orientation: "semi_polar",
    angle_deg: 32,
    seed_materials: [],
  },
  flip: { kind: "flip", name: "Retournement" },
};

const EXPECTED_PY_CODE = {
  deposition: 'Deposition(name="Dépôt", material="Si", recipe="ALD Conformal", thickness=Length(value=20, unit="nm"))',
  etch: 'Etch(name="Gravure", recipe="Anisotropic RIE", depth=Length(value=10, unit="nm"))',
  planarization: 'Planarization(name="Planarisation", target_level=Length(value=0, unit="nm"))',
  lithography:
    'Lithography(name="Lithographie", resist_material="Photoresist", thickness=Length(value=500, unit="nm"), openings=[(20, 40)])',
  chemical: 'ChemicalStep(name="Nettoyage")',
  resist_strip: 'ResistStrip(name="Retrait de résine", material="Photoresist")',
  faceted_growth:
    'FacetedGrowth(name="Croissance facettée", material="GaN", thickness=Length(value=10, unit="nm"), rate_c=1, rate_m=0.4, rate_sp=0.15, semi_polar_angle_deg=30, seed_materials=["GaN"])',
  epitaxial_growth:
    'EpitaxialGrowth(name="Croissance épitaxiale", material="GaN", thickness=Length(value=20, unit="nm"), orientation=GrowthOrientation.semi_polar, angle_deg=32)',
  flip: 'Flip(name="Retournement")',
};

test("pyStepCode renders the exact StructureForge constructor call for every step kind", () => {
  for (const [kind, step] of Object.entries(SAMPLE_STEPS)) {
    assert.equal(pyStepCode(step), EXPECTED_PY_CODE[kind], kind);
  }
});

test("stepSummary renders a human-readable one-liner for every step kind", () => {
  assert.equal(stepSummary(SAMPLE_STEPS.deposition), "Si · 20 nm · ALD Conformal");
  assert.equal(stepSummary(SAMPLE_STEPS.etch), "Anisotropic RIE · 10 nm");
  assert.equal(stepSummary(SAMPLE_STEPS.planarization), "jusqu'à 0 nm");
  assert.equal(stepSummary({ kind: "planarization", stop_material: "SiO2" }), "jusqu'au SiO2");
  assert.equal(stepSummary(SAMPLE_STEPS.lithography), "Photoresist · 1 ouverture(s)");
  assert.equal(stepSummary(SAMPLE_STEPS.chemical), "sans effet géométrique");
  assert.equal(stepSummary({ kind: "chemical", description: "bain HF" }), "bain HF");
  assert.equal(stepSummary(SAMPLE_STEPS.resist_strip), "Photoresist");
  assert.equal(stepSummary(SAMPLE_STEPS.faceted_growth), "GaN · +10 nm (C) · M×0.4 · SP×0.15 · SAG sur GaN");
  assert.equal(stepSummary(SAMPLE_STEPS.epitaxial_growth), "GaN · +20 nm · semi-polaire 32°");
  assert.equal(stepSummary(SAMPLE_STEPS.flip), "face avant ↔ face arrière");
});
