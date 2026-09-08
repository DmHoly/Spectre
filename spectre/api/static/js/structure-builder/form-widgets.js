/* Petits widgets de formulaire réutilisés par plusieurs types d'étape (matériaux, présets,
   lignes de sélectivité, paramètres process/estimations dérivées) - voir step-kinds.js pour ce
   qui, à l'inverse, est spécifique à un seul type d'étape. */

// Regroupe le menu déroulant par catégorie de matériau (la liste vient de la bibliothèque racine,
// library/materiaux.yml - voir spectre.core.registry). L'ordre des <optgroup> est fixe ; à
// l'intérieur, l'ordre du fichier est conservé. Une catégorie absente de MATERIAL_CATEGORY_LABELS
// (ou un matériau sans catégorie) retombe dans « Autres ».
const MATERIAL_CATEGORY_LABELS = {
  substrate: "Substrats",
  semiconductor: "Semi-conducteurs",
  dielectric: "Diélectriques",
  metal: "Métaux / TCO",
  resist: "Résines",
  other: "Autres",
};

function materialOptions(selectedValue) {
  const optionHtml = (m) =>
    `<option value="${escapeHtml(m.name)}" ${m.name === selectedValue ? "selected" : ""}>${escapeHtml(m.name)}</option>`;
  const known = new Set(Object.keys(MATERIAL_CATEGORY_LABELS));
  const bucketOf = (m) => (known.has(m.category) ? m.category : "other");
  return Object.keys(MATERIAL_CATEGORY_LABELS)
    .map((category) => {
      const inGroup = state.materials.filter((m) => bucketOf(m) === category);
      if (inGroup.length === 0) return "";
      return `<optgroup label="${escapeHtml(MATERIAL_CATEGORY_LABELS[category])}">${inGroup.map(optionHtml).join("")}</optgroup>`;
    })
    .join("");
}

// Composition InGaN/AlGaN à un taux précis, plutôt qu'un nom fixe de la bibliothèque - voir
// structureforge.core.materials.indium_gan/aluminum_gan côté serveur : la composition détermine
// elle-même le nom (In{x:.2f}Ga{1-x:.2f}N / Al{y:.2f}Ga{1-y:.2f}N), que run_simulation reconnaît
// et recompose (couleur/densité/indice) sans qu'aucun matériau n'ait besoin d'être enregistré
// nulle part au préalable - voir spectre.core.structures._graded_nitride_material.
const GRADED_NITRIDE_RE = /^(In|Al)(\d\.\d{2})Ga\d\.\d{2}N$/;

function gradedMaterialName(symbol, fractionPercent) {
  const x = Math.max(0, Math.min(100, fractionPercent)) / 100;
  return `${symbol}${x.toFixed(2)}Ga${(1 - x).toFixed(2)}N`;
}

// Un champ matériau qui, en plus des matériaux de la bibliothèque, propose de composer un
// InGaN/AlGaN à un taux précis. `id` nomme tout le groupe : le <select> est `${id}-select`, le
// mini-champ pourcentage `${id}-fraction`. `allowUnset` ajoute une option vide en tête (pour
// material_c/m/sp d'une croissance facettée, où vide retombe sur le matériau principal de
// l'étape - voir structureforge.process.steps.FacetedGrowth).
function gradedMaterialFieldHtml(id, label, selectedValue, { allowUnset = false, unsetLabel = "(même que le matériau principal)" } = {}) {
  const gradedMatch = GRADED_NITRIDE_RE.exec(selectedValue || "");
  const sentinel = gradedMatch ? (gradedMatch[1] === "In" ? "__in_gan__" : "__al_gan__") : null;
  const unsetOption = allowUnset ? `<option value="" ${!selectedValue ? "selected" : ""}>${unsetLabel}</option>` : "";
  const baseOptions = materialOptions(sentinel ? "" : selectedValue);
  const fractionPercent = gradedMatch ? Math.round(parseFloat(gradedMatch[2]) * 100) : 20;
  return `
    <div>
      <label>${label}</label>
      <select class="field" id="${id}-select">
        ${unsetOption}
        ${baseOptions}
        <optgroup label="Nitrures à composition (taux %)">
          <option value="__in_gan__" ${sentinel === "__in_gan__" ? "selected" : ""}>InGaN</option>
          <option value="__al_gan__" ${sentinel === "__al_gan__" ? "selected" : ""}>AlGaN</option>
        </optgroup>
      </select>
      <div id="${id}-fraction-wrap" style="margin-top:6px;display:${sentinel ? "" : "none"};">
        <label id="${id}-fraction-label">Taux (%)</label>
        <input class="field" id="${id}-fraction" type="number" min="0" max="100" step="1" value="${fractionPercent}">
      </div>
    </div>`;
}

function wireGradedMaterialField(id) {
  const select = document.getElementById(`${id}-select`);
  const wrap = document.getElementById(`${id}-fraction-wrap`);
  const label = document.getElementById(`${id}-fraction-label`);
  select.addEventListener("change", () => {
    const graded = select.value === "__in_gan__" || select.value === "__al_gan__";
    wrap.style.display = graded ? "" : "none";
    if (label) label.textContent = select.value === "__al_gan__" ? "Taux d'aluminium (%)" : "Taux d'indium (%)";
  });
}

// La valeur effective à écrire dans le champ de l'étape (material/material_c/...) - le nom gradé
// composé si l'option spéciale est choisie, sinon directement la valeur du <select> (chaîne vide
// pour l'option "même que le matériau principal", à l'appelant de la traduire en null si besoin).
function gradedMaterialValue(id) {
  const select = document.getElementById(`${id}-select`);
  if (select.value === "__in_gan__" || select.value === "__al_gan__") {
    const symbol = select.value === "__in_gan__" ? "In" : "Al";
    return gradedMaterialName(symbol, parseFloat(document.getElementById(`${id}-fraction`).value) || 0);
  }
  return select.value;
}

// Pré-remplissage à l'édition : reconstruit l'état du groupe (option choisie + taux) depuis le
// nom de matériau déjà stocké sur l'étape - `materialName` peut être null/undefined (material_c
// etc. non renseigné sur cette étape).
function fillGradedMaterialField(id, materialName) {
  const select = document.getElementById(`${id}-select`);
  const wrap = document.getElementById(`${id}-fraction-wrap`);
  const match = GRADED_NITRIDE_RE.exec(materialName || "");
  if (match) {
    select.value = match[1] === "In" ? "__in_gan__" : "__al_gan__";
    document.getElementById(`${id}-fraction`).value = Math.round(parseFloat(match[2]) * 100);
    wrap.style.display = "";
    const label = document.getElementById(`${id}-fraction-label`);
    if (label) label.textContent = match[1] === "Al" ? "Taux d'aluminium (%)" : "Taux d'indium (%)";
  } else {
    select.value = materialName || "";
    wrap.style.display = "none";
  }
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
