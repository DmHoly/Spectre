/* Petits widgets de formulaire réutilisés par plusieurs types d'étape (matériaux, présets,
   lignes de sélectivité, paramètres process/estimations dérivées) - voir step-kinds.js pour ce
   qui, à l'inverse, est spécifique à un seul type d'étape. */

function materialOptions(selectedValue) {
  return state.materials
    .map((m) => `<option value="${escapeHtml(m.name)}" ${m.name === selectedValue ? "selected" : ""}>${escapeHtml(m.name)}</option>`)
    .join("");
}

function presetOptionsHtml(kind) {
  const entries = [
    ...state.stepPresets.presets.map((p) => ({ ...p, scope: "preset" })),
    ...state.stepPresets.partagees.map((p) => ({ ...p, scope: "partagee" })),
    ...state.stepPresets.projet.map((p) => ({ ...p, scope: "projet" })),
  ].filter((p) => p.payload.kind === kind);
  const scopeSuffix = { preset: " (préset)", partagee: " (partagée)", projet: "" };
  return entries
    .map((p) => `<option value="${p.scope}::${encodeURIComponent(p.name)}">${escapeHtml(p.name)}${scopeSuffix[p.scope]}</option>`)
    .join("");
}

function findStepPreset(scope, name) {
  const bucket = scope === "preset" ? state.stepPresets.presets : scope === "partagee" ? state.stepPresets.partagees : state.stepPresets.projet;
  return (bucket || []).find((p) => p.name === name) || null;
}

function recipeOptions(kind, selectedValue) {
  return (state.recipes[kind] || [])
    .map((r) => `<option value="${escapeHtml(r.name)}" ${r.name === selectedValue ? "selected" : ""}>${escapeHtml(r.name)}</option>`)
    .join("");
}

function recipeHint(kind, name) {
  const recipe = (state.recipes[kind] || []).find((r) => r.name === name);
  if (!recipe) return "";
  const mode = modeSummary(recipe.mode, recipe.angle_deg);
  return recipe.notes ? `${mode} — ${recipe.notes}` : mode;
}

// The recipe carries mode/angle(/selectivity for etch) itself now (see structureforge.core.
// recipes) - the form only needs to pick a name and show what it does, and optionally jump
// straight to one via a saved préset.
function wireRecipeField(kind) {
  const recipeSelect = document.getElementById("f-recipe");
  const hint = document.getElementById("f-recipe-hint");
  const update = () => {
    hint.textContent = recipeHint(kind, recipeSelect.value);
  };
  recipeSelect.addEventListener("change", update);
  update();
  document.getElementById("f-preset").addEventListener("change", (e) => {
    const value = e.target.value;
    if (!value) return;
    const [scope, name] = value.split("::");
    const preset = findStepPreset(scope, decodeURIComponent(name));
    if (!preset) return;
    recipeSelect.value = preset.payload.recipe;
    update();
  });
}

function parseCommaList(text) {
  return text
    .trim()
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

// Whether the semi-polar facets or the c-plane top wins the race, so the user knows if they're
// heading for a flat-top pencil or a sharp pyramidal tip before running the simulation.
function wireFacetedGrowthTipHint() {
  const hint = document.getElementById("f-tip-hint");
  const update = () => {
    const rateC = parseFloat(document.getElementById("f-rate-c").value) || 0;
    const rateSp = parseFloat(document.getElementById("f-rate-sp").value) || 0;
    const angle = parseFloat(document.getElementById("f-angle-sp").value) || 30;
    const spVertical = rateSp * Math.cos((angle * Math.PI) / 180);
    if (rateC <= 0 && rateSp <= 0) {
      hint.textContent = "";
      return;
    }
    if (rateC >= spVertical) {
      const ratio = spVertical > 0 ? (rateC / spVertical).toFixed(2) : "∞";
      hint.textContent = `→ le plan C domine (×${ratio} vs SP vertical) — pointe plate attendue`;
    } else {
      const ratio = rateC > 0 ? (spVertical / rateC).toFixed(2) : "∞";
      hint.textContent = `→ le semipolaire domine (×${ratio} vs C) — pointe aiguë / pyramidale attendue`;
    }
  };
  ["f-rate-c", "f-rate-sp", "f-angle-sp"].forEach((id) => document.getElementById(id).addEventListener("input", update));
  update();
}

function wireEpitaxialOrientationToggle() {
  const orientationSelect = document.getElementById("f-orientation");
  const angleWrap = document.getElementById("f-angle-wrap");
  const update = () => {
    angleWrap.style.display = orientationSelect.value === "semi_polar" ? "" : "none";
  };
  orientationSelect.addEventListener("change", update);
  update();
}

function parseOpenings(text) {
  if (!text.trim()) return [];
  return text.split(",").map((part) => {
    const [a, b] = part.split("-").map((n) => parseFloat(n.trim()));
    return [a, b];
  });
}

// Un réseau périodique d'ouvertures (pas + diamètre) plutôt que de taper chaque plage à la main -
// écrit dans le même champ texte que parseOpenings lit déjà (voir le formulaire de lithographie
// dans step-kinds.js), pas de nouveau format ni de lien vivant après coup.
function generatePeriodicOpenings(pitchNm, diameterNm, domainWidthNm, count, offsetNm) {
  if (!(pitchNm > 0) || !(diameterNm > 0) || diameterNm > pitchNm) return [];
  const n = count && count >= 1 ? Math.floor(count) : Math.max(1, Math.floor((domainWidthNm - diameterNm) / pitchNm) + 1);
  const span = (n - 1) * pitchNm;
  const startCenter = offsetNm != null && !Number.isNaN(offsetNm) ? offsetNm : (domainWidthNm - span) / 2;
  const round = (v) => Math.round(v * 1000) / 1000;
  const openings = [];
  for (let i = 0; i < n; i++) {
    const center = startCenter + i * pitchNm;
    const a = Math.max(0, center - diameterNm / 2);
    const b = Math.min(domainWidthNm, center + diameterNm / 2);
    if (b > a) openings.push([round(a), round(b)]);
  }
  return openings;
}

const MODE_LABELS = { conformal: "conforme", directional: "directionnel", isotropic: "isotrope", anisotropic: "anisotrope" };

function modeSummary(mode, angle_deg) {
  const label = MODE_LABELS[mode] || mode;
  return angle_deg ? `${label} (${angle_deg}°)` : label;
}
