"use strict";

/* Unit tests for the structure-builder step-kind registry (spectre/plugins/structures/static/builder/
   step-kinds.js) and the small pure helpers it depends on - the part of the modularization that
   replaced nine scattered per-kind branches with one entry per step kind. Run with:

     node --test

   No external dependency: Node's built-in test runner loads the real production files as-is (see
   helpers/load-structure-builder.js) - not a reimplementation, the actual shipped source. */

const test = require("node:test");
const assert = require("node:assert/strict");
const { loadStructureBuilder } = require("./helpers/load-structure-builder");

const {
  STEP_KIND_DEFS,
  STEP_KINDS,
  CAMPAIGN_FIELD_OPTIONS,
  PY_STEP_CLASS,
  stepSummary,
  pyStepCode,
  modeSummary,
  parseOpenings,
  pyStr,
  pyLength,
  pyDict,
  toNm,
  facetedGrowthTipHint,
} =
  loadStructureBuilder(
    ["form-widgets.js", "code-export.js", "step-kinds.js"],
    [
      "facetedGrowthTipHint",
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

test("STEP_KIND_DEFS registers exactly the ten known step kinds", () => {
  const kinds = Object.keys(STEP_KIND_DEFS).sort();
  assert.deepEqual(kinds, [
    "chemical",
    "deposition",
    "epitaxial_growth",
    "etch",
    "facet_envelope",
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
  facet_envelope: {
    kind: "facet_envelope",
    name: "Pyramide",
    material: "GaN",
    c_plane: false,
    m_plane: false,
    semi_polar_angle_deg: 30,
    seed_materials: ["GaN"],
    top_level: { value: 40, unit: "nm" },
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
  facet_envelope:
    'FacetEnvelope(name="Pyramide", material="GaN", c_plane=False, semi_polar_angle_deg=30, top_level=Length(value=40, unit="nm"), seed_materials=["GaN"])',
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
  assert.equal(stepSummary(SAMPLE_STEPS.facet_envelope), "GaN · SP 30° · tronqué à 40 nm · sur GaN");
  assert.equal(stepSummary({ kind: "facet_envelope", material: "GaN", c_plane: true, m_plane: true, semi_polar_angle_deg: null, seed_materials: [] }), "GaN · C + M");
  assert.equal(stepSummary(SAMPLE_STEPS.epitaxial_growth), "GaN · +20 nm · semi-polaire 32°");
  assert.equal(stepSummary(SAMPLE_STEPS.flip), "face avant ↔ face arrière");
});

// Un document qui garde la valeur de chaque champ, juste ce que buildFromForm/fillFields lisent et
// écrivent - le document factice du harnais rend un élément neuf à chaque appel, sans mémoire.
function withFormDocument(values, fn) {
  const elements = new Map();
  const element = (id) => {
    if (!elements.has(id)) elements.set(id, { value: values[id] ?? "", style: {}, textContent: "", appendChild() {} });
    return elements.get(id);
  };
  const saved = global.document;
  global.document = { getElementById: element, createElement: () => ({}) };
  try {
    return fn(element);
  } finally {
    global.document = saved;
  }
}

// Une coquille partie de la pointe : flancs qui ne poussent pas (plan M à 0), facettes inversées
// à 0.3 en InGaN 30 %.
const SHELL_FORM = {
  "f-material-select": "GaN",
  "f-thickness": "20",
  "f-thickness-unit": "nm",
  "f-rate-c": "1",
  "f-rate-m": "0",
  "f-rate-sp": "0.5",
  "f-rate-sp-inv": "0.3",
  "f-angle-sp": "30",
  "f-seed-materials": "GaN",
  "f-material-sp-inv-select": "__in_gan__",
  "f-material-sp-inv-fraction": "30",
};

test("faceted_growth: the inverted semi-polar rate and material go from the form to the step and back", () => {
  const def = STEP_KIND_DEFS.faceted_growth;
  const step = withFormDocument(SHELL_FORM, () => def.buildFromForm("Coquille"));
  assert.equal(step.rate_sp_inv, 0.3);
  assert.equal(step.material_sp_inv, "In0.30Ga0.70N");
  assert.equal(step.material_sp, null);
  assert.equal(step.rate_m, 0);
  const again = withFormDocument({}, () => {
    def.fillFields(step);
    return def.buildFromForm("Coquille");
  });
  assert.deepEqual(again, step);
});

test("faceted_growth: a step saved before the inverted facets opens with them off and exports as before", () => {
  const def = STEP_KIND_DEFS.faceted_growth;
  const old = SAMPLE_STEPS.faceted_growth; // ni rate_sp_inv ni material_sp_inv
  const step = withFormDocument({}, (element) => {
    def.fillFields(old);
    assert.equal(element("f-rate-sp-inv").value, 0);
    return def.buildFromForm(old.name);
  });
  assert.equal(step.rate_sp_inv, 0);
  assert.equal(step.material_sp_inv, null);
  assert.equal(pyStepCode(step), EXPECTED_PY_CODE.faceted_growth);
  assert.equal(stepSummary(step), stepSummary(old));
});

test("faceted_growth: summary and Python code name the inverted facets only when they are used", () => {
  const shell = { ...SAMPLE_STEPS.faceted_growth, rate_m: 0, rate_sp_inv: 0.3, material_sp_inv: "In0.30Ga0.70N" };
  assert.equal(stepSummary(shell), "GaN · +10 nm (C) · M×0 · SP×0.15 · SP inv×0.3 · SPinv=In0.30Ga0.70N · SAG sur GaN");
  assert.equal(
    pyStepCode(shell),
    'FacetedGrowth(name="Croissance facettée", material="GaN", thickness=Length(value=10, unit="nm"), rate_c=1, rate_m=0, rate_sp=0.15, rate_sp_inv=0.3, semi_polar_angle_deg=30, material_sp_inv="In0.30Ga0.70N", seed_materials=["GaN"])'
  );
  const off = { ...SAMPLE_STEPS.faceted_growth, rate_sp_inv: 0, material_sp_inv: null };
  assert.equal(stepSummary(off), stepSummary(SAMPLE_STEPS.faceted_growth));
  assert.equal(pyStepCode(off), EXPECTED_PY_CODE.faceted_growth);
});

test("facetedGrowthTipHint: flat top when rate_sp > rate_c·cos θ, as the engine decides", () => {
  // les deux cas vérifiés sur un fil de 60 nm : le sommet rétrécit, puis s'élargit
  assert.match(facetedGrowthTipHint(1, 0.5, 45), /pointe aiguë/);
  assert.match(facetedGrowthTipHint(1, 1.2, 45), /pointe plate/);
  // plan C immobile : le semipolaire élargit le sommet ; semipolaire immobile : il le referme
  assert.match(facetedGrowthTipHint(0, 0.5, 30), /pointe plate/);
  assert.match(facetedGrowthTipHint(1, 0, 30), /pointe aiguë/);
  assert.equal(facetedGrowthTipHint(0, 0, 30), "");
});
