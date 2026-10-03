/* Écran 3 (variations et échantillons) : cliquer une étape du process flow, le substrat, ou une
   couche du dessin pour choisir *n'importe quel* paramètre à faire varier - une épaisseur, une
   vitesse, un angle, le taux d'indium d'un InGaN, le pas d'un réseau de lithographie, un matériau,
   une recette, ou un paramètre déclaré (un dopage...) - en linéaire, en logarithmique (décades) ou
   en liste de valeurs, puis un tableau façon Excel, une ligne par combinaison, avec les noms de
   wafers et emplacements des échantillons réels. Sans variation, le tableau dégénère naturellement
   à une seule ligne (la structure telle quelle). Le plan ({factors: [{step_index, field, values,
   scale, label}]}) est celui que preview_campaign/launch_campaign attendent côté serveur (voir
   spectre.core.structures.VariantFactor pour la syntaxe de `field`), lu par experience-launch.js
   via state.campaignPlan. `scale` garde la répartition choisie : une variation en échelle log le
   reste quand on la rouvre, et la campagne l'enregistre. */

let variationEditingStepIndex = null; // index de l'étape (-1 = substrat) dont l'inspecteur montre le formulaire de variation
let variationParams = []; // paramètres variables de cette étape (voir variableParams)
let variationMode = "linear"; // "linear" | "log" | "explicit" pour un paramètre numérique

const PARAM_FIELD_LABELS = {
  thickness: "Épaisseur",
  depth: "Profondeur",
  target_level: "Niveau cible",
  domain_width: "Largeur du domaine",
  rate_c: "Vitesse plan C",
  rate_m: "Vitesse plan M",
  rate_sp: "Vitesse semipolaire",
  semi_polar_angle_deg: "Angle semipolaire",
  angle_deg: "Angle",
  material: "Matériau",
  material_c: "Matériau plan C",
  material_m: "Matériau plan M",
  material_sp: "Matériau semipolaire",
  resist_material: "Résine",
  stop_material: "Matériau d'arrêt",
  recipe: "Recette",
  orientation: "Orientation",
};
const PARAM_UNITS = { semi_polar_angle_deg: "°", angle_deg: "°", rate_c: "× réf.", rate_m: "× réf.", rate_sp: "× réf." };
const MATERIAL_PARAM_FIELDS = new Set(["material", "material_c", "material_m", "material_sp", "resist_material", "stop_material"]);
const ORIENTATION_CHOICES = [
  ["c_plane", "Plan C [0001]"],
  ["m_plane", "Plan M {10-10}"],
  ["semi_polar", "Semi-polaire"],
];
const NON_VARIABLE_STEP_KEYS = new Set(["kind", "name", "description", "declaredParams", "brick_group_id", "brick_name", "parameters", "seed_materials", "openings"]);

function unitLabel(unit) {
  return unit === "um" ? "µm" : unit === "A" ? "Å" : unit || "";
}

function isLengthValue(value) {
  return value && typeof value === "object" && "value" in value && "unit" in value;
}

function withCurrentOption(options, current) {
  return current && !options.some(([value]) => value === current) ? [[current, current], ...options] : options;
}

function materialChoices(current) {
  return withCurrentOption(
    state.materials.map((m) => [m.name, m.name]),
    current
  );
}

// Pas et diamètre d'un réseau d'ouvertures existant (le générateur de la lithographie écrit une
// liste de plages, pas ces deux nombres) - pour proposer de les faire varier.
// Même lecture que spectre.core.structures._openings_with : une ouverture coupée par un bord du
// domaine garde le centre qu'elle aurait eu entière.
function openingsGeometry(openings) {
  const sorted = [...openings].sort((a, b) => a[0] - b[0]);
  const domain = toNm(substrateSpec().domain_width);
  const full = Math.max(...sorted.map(([a, b]) => b - a));
  const centers = sorted.map(([a, b]) => {
    if (b - a < full - 1e-6 && a <= 1e-6) return b - full / 2;
    if (b - a < full - 1e-6 && b >= domain - 1e-6) return a + full / 2;
    return (a + b) / 2;
  });
  return {
    diameter: Math.round(full * 1000) / 1000,
    pitch: centers.length >= 2 ? Math.round((centers[1] - centers[0]) * 1000) / 1000 : null,
  };
}

// Tout ce qu'on peut faire varier sur une étape (ou le substrat, index -1) : ses propres champs
// (nombres, longueurs, choix), le taux d'un nitrure à composition, le réseau d'une lithographie,
// ses paramètres déclarés. Les champs "principaux" du type d'étape (step-kinds.js, campaignFields)
// viennent en tête.
function variableParams(stepIndex) {
  if (stepIndex === -1) {
    const substrate = substrateSpec();
    return [
      { field: "thickness", label: "Épaisseur", type: "number", unit: unitLabel(substrate.thickness.unit), current: substrate.thickness.value },
      { field: "domain_width", label: "Largeur du domaine", type: "number", unit: unitLabel(substrate.domain_width.unit), current: substrate.domain_width.value },
      { field: "material", label: "Matériau", type: "choice", choices: materialChoices(substrate.material), current: substrate.material },
    ];
  }
  const step = state.steps[stepIndex];
  if (!step) return [];
  const primary = (CAMPAIGN_FIELD_OPTIONS[step.kind] || []).map(([field]) => field);
  const keys = Object.keys(step)
    .filter((key) => !NON_VARIABLE_STEP_KEYS.has(key))
    .sort((a, b) => Number(primary.includes(b)) - Number(primary.includes(a)));
  const params = [];
  keys.forEach((key) => {
    const value = step[key];
    const label = PARAM_FIELD_LABELS[key] || key;
    if (key === "angle_deg" && step.orientation !== "semi_polar") return; // sans effet hors semi-polaire
    if (isLengthValue(value)) {
      params.push({ field: key, label, type: "number", unit: unitLabel(value.unit), current: value.value });
    } else if (typeof value === "number") {
      params.push({ field: key, label, type: "number", unit: PARAM_UNITS[key] || "", current: value });
    } else if (typeof value === "string" && value) {
      if (MATERIAL_PARAM_FIELDS.has(key)) {
        params.push({ field: key, label, type: "choice", choices: materialChoices(value), current: value });
        const graded = GRADED_NITRIDE_RE.exec(value);
        if (graded) {
          params.push({
            field: `${key}.fraction`,
            label: `Taux ${graded[1] === "In" ? "d'indium" : "d'aluminium"}${key === "material" ? "" : ` (${label.toLowerCase()})`}`,
            type: "number",
            unit: "%",
            current: Math.round(parseFloat(graded[2]) * 100),
          });
        }
      } else if (key === "recipe") {
        const recipes = (state.recipes[step.kind] || []).map((r) => [r.name, r.name]);
        params.push({ field: key, label, type: "choice", choices: withCurrentOption(recipes, value), current: value });
      } else if (key === "orientation") {
        params.push({ field: key, label, type: "choice", choices: ORIENTATION_CHOICES, current: value });
      }
    }
  });
  if (step.kind === "lithography" && step.openings && step.openings.length) {
    const { pitch, diameter } = openingsGeometry(step.openings);
    if (pitch != null) params.push({ field: "openings.pitch", label: "Pas du réseau", type: "number", unit: "nm", current: pitch });
    params.push({ field: "openings.diameter", label: "Diamètre d'ouverture", type: "number", unit: "nm", current: diameter });
  }
  (step.declaredParams || []).forEach((p) => {
    if (!p.name) return;
    const numeric = typeof p.value === "number";
    params.push({ field: `declared:${p.name}`, label: p.name, declared: true, type: numeric ? "number" : "choice", free: !numeric, unit: "", current: p.value });
  });
  return params;
}

function isVariableTarget(stepIndex) {
  return variableParams(stepIndex).length > 0;
}

function variationTargetName(stepIndex) {
  return stepIndex === -1 ? "Substrat" : state.steps[stepIndex] ? state.steps[stepIndex].name : "";
}

function paramDisplayLabel(param) {
  return `${param.label}${param.unit && param.unit !== "× réf." ? ` (${param.unit})` : ""}`;
}

// -- valeurs ----------------------------------------------------------------------------------

function parseNumber(text) {
  const value = Number(String(text).trim().replace(",", "."));
  return String(text).trim() !== "" && Number.isFinite(value) ? value : NaN;
}

function roundSignificant(value, digits) {
  return value === 0 ? 0 : parseFloat(value.toPrecision(digits));
}

function linearValues(min, max, count) {
  if (!Number.isFinite(min) || !Number.isFinite(max) || !Number.isInteger(count) || count < 2) return [];
  const step = (max - min) / (count - 1);
  return Array.from({ length: count }, (_, i) => roundSignificant(min + step * i, 6));
}

// Espacement géométrique (même rapport d'une valeur à la suivante) : 1e17 → 1e19 en 5 points donne
// 1e17, 3.16e17, 1e18, 3.16e18, 1e19. Arrondi à 3 chiffres significatifs, comme on les écrit.
function logValues(min, max, count) {
  if (!(min > 0) || !(max > 0) || !Number.isInteger(count) || count < 2) return [];
  const a = Math.log10(min);
  const b = Math.log10(max);
  return Array.from({ length: count }, (_, i) => roundSignificant(10 ** (a + ((b - a) * i) / (count - 1)), 3));
}

function explicitNumberValues() {
  return document
    .getElementById("variation-values")
    .value.split(/[;,\s]+/)
    .filter(Boolean)
    .map(parseNumber)
    .filter((v) => !Number.isNaN(v));
}

function currentParam() {
  const field = document.getElementById("variation-field-select").value;
  return variationParams.find((p) => p.field === field) || null;
}

// Les valeurs que produirait le formulaire tel qu'il est rempli - {values, scale, error}.
function collectVariationValues() {
  const param = currentParam();
  if (!param) return { values: [], error: "Choisissez un paramètre à faire varier." };
  if (param.type === "choice") {
    if (param.free) {
      const values = document
        .getElementById("variation-choice-free")
        .value.split(",")
        .map((v) => v.trim())
        .filter(Boolean);
      return { values, scale: "list", error: values.length ? null : "Renseignez au moins une valeur." };
    }
    const values = [...document.querySelectorAll("#variation-choice-list input:checked")].map((cb) => cb.value);
    return { values, scale: "list", error: values.length ? null : "Cochez au moins une valeur à comparer." };
  }
  if (variationMode === "explicit") {
    const values = explicitNumberValues();
    return { values, scale: "list", error: values.length ? null : "Renseignez au moins une valeur." };
  }
  const min = parseNumber(document.getElementById("variation-min").value);
  const max = parseNumber(document.getElementById("variation-max").value);
  const count = parseInt(document.getElementById("variation-count").value, 10);
  if (variationMode === "log") {
    const values = logValues(min, max, count);
    return { values, scale: "log", error: values.length ? null : "En échelle log, le minimum et le maximum doivent être strictement positifs (au moins 2 points)." };
  }
  const values = linearValues(min, max, count);
  return { values, scale: "linear", error: values.length ? null : "Renseignez un minimum, un maximum et au moins 2 points." };
}

function renderVariationPreview() {
  const preview = document.getElementById("variation-preview");
  const { values, error } = collectVariationValues();
  if (error || !values.length) {
    preview.innerHTML = error && document.activeElement && document.activeElement.closest("#variation-form-section") ? `<span class="sb-variation-preview__warn">${escapeHtml(error)}</span>` : "";
    return;
  }
  const shown = values.slice(0, 12).map((v) => `<span class="sb-variation-preview__value">${escapeHtml(formatParamValue(v))}</span>`).join("");
  preview.innerHTML = `<span class="sb-variation-preview__arrow" aria-hidden="true">→</span>${shown}${values.length > 12 ? `<span class="help">+${values.length - 12}</span>` : ""}<span class="sb-variation-preview__count">${values.length} valeur${values.length > 1 ? "s" : ""}</span>`;
}

// -- formulaire -------------------------------------------------------------------------------

function setVariationMode(mode) {
  variationMode = mode;
  ["linear", "log", "explicit"].forEach((m) => document.getElementById(`variation-mode-${m}`).classList.toggle("active", m === mode));
  document.getElementById("variation-range-fields").hidden = mode === "explicit";
  document.getElementById("variation-explicit-fields").hidden = mode !== "explicit";
  renderVariationPreview();
}

["linear", "log", "explicit"].forEach((mode) => {
  document.getElementById(`variation-mode-${mode}`).addEventListener("click", () => {
    const param = currentParam();
    // passer en log depuis une plage linéaire qui part de 0 : on repart d'une décade autour de la valeur actuelle
    if (mode === "log" && param && !(parseNumber(document.getElementById("variation-min").value) > 0)) fillRangeDefaults(param, "log");
    setVariationMode(mode);
  });
});

// Suggère une plage autour de la valeur actuelle : ±50 % en linéaire, une décade de part et d'autre
// en log (un dopage à 1e18 → 1e17 … 1e19).
function fillRangeDefaults(param, mode) {
  const current = typeof param.current === "number" ? param.current : 0;
  let min;
  let max;
  if (mode === "log") {
    const base = current > 0 ? current : 1;
    min = base / 10;
    max = base * 10;
  } else if (current === 0) {
    min = 0;
    max = 10;
  } else {
    min = roundSignificant(current * 0.5, 3);
    max = roundSignificant(current * 1.5, 3);
  }
  document.getElementById("variation-min").value = formatNumberInput(roundSignificant(min, 6));
  document.getElementById("variation-max").value = formatNumberInput(roundSignificant(max, 6));
  document.getElementById("variation-count").value = "3";
}

// Un grand nombre (dopage, concentration) ou une très petite valeur appelle naturellement une échelle log.
function prefersLog(param) {
  const v = Math.abs(typeof param.current === "number" ? param.current : 0);
  return v >= 1e5 || (v > 0 && v < 1e-3);
}

// Remplit le formulaire pour le paramètre choisi : la variation déjà définie dessus s'il y en a une
// (dans son échelle d'origine - log reste log), sinon une plage suggérée autour de la valeur actuelle.
function fillVariationForm() {
  const param = currentParam();
  const hint = document.getElementById("variation-current-hint");
  const numberFields = document.getElementById("variation-number-fields");
  const choiceFields = document.getElementById("variation-choice-fields");
  if (!param) {
    hint.textContent = "";
    numberFields.hidden = true;
    choiceFields.hidden = true;
    renderVariationPreview();
    return;
  }
  const existing = state.variationFactors.find((f) => f.step_index === variationEditingStepIndex && f.field === param.field);
  const currentText = param.type === "number" ? formatParamValue(param.current) : param.choices ? (param.choices.find(([v]) => v === param.current) || [param.current, param.current])[1] : String(param.current);
  hint.textContent = `Valeur actuelle : ${currentText}${param.unit && param.type === "number" ? ` ${param.unit}` : ""}${param.declared ? " · paramètre déclaré" : ""}`;
  numberFields.hidden = param.type !== "number";
  choiceFields.hidden = param.type !== "choice";

  if (param.type === "number") {
    const unit = param.unit && param.unit !== "× réf." ? ` (${param.unit})` : "";
    document.getElementById("variation-min-label").textContent = `Min${unit}`;
    document.getElementById("variation-max-label").textContent = `Max${unit}`;
    document.getElementById("variation-values-label").textContent = `Valeurs${unit}`;
    if (existing) {
      const values = existing.values;
      document.getElementById("variation-min").value = formatNumberInput(values[0]);
      document.getElementById("variation-max").value = formatNumberInput(values[values.length - 1]);
      document.getElementById("variation-count").value = String(Math.max(2, values.length));
      document.getElementById("variation-values").value = values.map(formatNumberInput).join(", ");
      setVariationMode(existing.scale === "log" ? "log" : existing.scale === "list" || values.length < 2 ? "explicit" : "linear");
    } else {
      const mode = prefersLog(param) ? "log" : "linear";
      fillRangeDefaults(param, mode);
      document.getElementById("variation-values").value = "";
      setVariationMode(mode);
    }
  } else {
    const list = document.getElementById("variation-choice-list");
    const free = document.getElementById("variation-choice-free");
    list.hidden = Boolean(param.free);
    free.hidden = !param.free;
    const chosen = new Set(existing ? existing.values.map(String) : [String(param.current)]);
    if (param.free) {
      free.value = existing ? existing.values.join(", ") : String(param.current ?? "");
    } else {
      list.innerHTML = param.choices
        .map(
          ([value, text]) => `
          <label class="sb-choice">
            <input type="checkbox" value="${escapeHtml(value)}" ${chosen.has(String(value)) ? "checked" : ""}>
            <span>${escapeHtml(text)}</span>${value === param.current ? `<span class="sb-choice__now">actuel</span>` : ""}
          </label>`
        )
        .join("");
    }
    renderVariationPreview();
  }
}

// Ce que l'inspecteur montre à l'écran variations (appelé par renderInspector, inspector.js).
function renderVariationInspector() {
  if (variationEditingStepIndex !== null && (variationEditingStepIndex === -1 || state.steps[variationEditingStepIndex])) {
    showInspectorSection("variation-form-section");
  } else {
    showInspectorEmpty("Cliquez une étape du flow, le substrat, ou une couche du dessin, pour choisir un paramètre à faire varier.");
  }
}

// Point d'entrée commun au clic sur une couche du dessin et au clic sur une étape du flow (voir
// step-list.js) - ouvre le formulaire de variation pour cette étape (ou le substrat, -1) dans
// l'inspecteur, sur `field` si précisé (clic sur une variation déjà définie).
function startVaryingLayer(stepIndex, field) {
  const params = variableParams(stepIndex);
  if (!params.length) return;
  variationEditingStepIndex = stepIndex;
  variationParams = params;
  showInspectorSection("variation-form-section");
  document.getElementById("variation-form-title").textContent = stepIndex === -1 ? "Substrat" : `${state.steps[stepIndex].name} (étape ${stepIndex + 1})`;
  const own = params.filter((p) => !p.declared);
  const declared = params.filter((p) => p.declared);
  const optionHtml = (p) => {
    const varied = state.variationFactors.some((f) => f.step_index === stepIndex && f.field === p.field);
    return `<option value="${escapeHtml(p.field)}">${escapeHtml(paramDisplayLabel(p))}${varied ? " ✓" : ""}</option>`;
  };
  document.getElementById("variation-field-select").innerHTML =
    (declared.length ? `<optgroup label="Réglages de l'étape">${own.map(optionHtml).join("")}</optgroup>` : own.map(optionHtml).join("")) +
    (declared.length ? `<optgroup label="Paramètres déclarés">${declared.map(optionHtml).join("")}</optgroup>` : "");
  const firstVaried = state.variationFactors.find((f) => f.step_index === stepIndex);
  const target = field || (firstVaried && firstVaried.field) || params[0].field;
  document.getElementById("variation-field-select").value = target;
  fillVariationForm();
  renderRail();
  highlightSelectedLayer();
  document.getElementById("variation-field-select").focus();
}

function cancelVaryingLayer() {
  variationEditingStepIndex = null;
  variationParams = [];
  renderVariationInspector();
  renderRail();
  highlightSelectedLayer();
}

document.getElementById("cancel-variation-btn").addEventListener("click", cancelVaryingLayer);
document.getElementById("variation-field-select").addEventListener("change", fillVariationForm);
const variationFormSection = document.getElementById("variation-form-section");
variationFormSection.addEventListener("input", renderVariationPreview);
variationFormSection.addEventListener("change", (e) => {
  if (e.target.id !== "variation-field-select") renderVariationPreview();
});
variationFormSection.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && e.target.matches("input")) {
    e.preventDefault();
    addVariationFromForm();
  }
});

function addVariationFromForm() {
  clearError();
  if (variationEditingStepIndex === null) return;
  const stepIndex = variationEditingStepIndex;
  const param = currentParam();
  const { values, scale, error } = collectVariationValues();
  if (error) {
    showError(new Error(error));
    return;
  }
  const label = `${paramDisplayLabel(param)} — ${variationTargetName(stepIndex)}`;
  state.variationFactors = state.variationFactors.filter((f) => !(f.step_index === stepIndex && f.field === param.field));
  state.variationFactors.push({ step_index: stepIndex, field: param.field, field_label: label, values, scale });
  cancelVaryingLayer();
  renderVariationFactorsList();
  refreshVariationTable();
}

document.getElementById("add-variation-btn").addEventListener("click", addVariationFromForm);

function removeVariationFactor(index) {
  state.variationFactors.splice(index, 1);
  renderVariationFactorsList();
  refreshVariationTable();
  renderRail();
}

const SCALE_BADGES = { log: "log", linear: "lin.", list: "liste" };

function renderVariationFactorsList() {
  const list = document.getElementById("variation-factors-list");
  if (state.variationFactors.length === 0) {
    list.innerHTML = `<div class="sb-factors__empty">Aucune variation définie : un seul échantillon sera lancé, tel quel.</div>`;
    return;
  }
  const combos = state.variationFactors.reduce((acc, f) => acc * f.values.length, 1);
  list.innerHTML =
    state.variationFactors
      .map(
        (f, i) => `
      <div class="sb-factor">
        <button class="sb-factor__body js-edit-variation-factor" type="button" data-step="${f.step_index}" data-field="${escapeHtml(f.field)}" title="Modifier cette variation">
          <span class="sb-factor__label">${escapeHtml(f.field_label)}<span class="sb-factor__scale sb-factor__scale--${f.scale || "linear"}">${SCALE_BADGES[f.scale] || ""}</span></span>
          <span class="sb-factor__values mono">${f.values.map((v) => escapeHtml(formatParamValue(v))).join(" · ")}</span>
        </button>
        <button class="sb-iconbtn sb-iconbtn--sm sb-iconbtn--danger js-remove-variation-factor" data-index="${i}" type="button" aria-label="Retirer cette variation" title="Retirer">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M6 18L18 6"/></svg>
        </button>
      </div>`
      )
      .join("") +
    `<div class="sb-factors__total">${state.variationFactors.length > 1 ? `${state.variationFactors.map((f) => f.values.length).join(" × ")} = ` : ""}<strong>${combos} échantillon${combos > 1 ? "s" : ""}</strong></div>`;
  list.querySelectorAll(".js-remove-variation-factor").forEach((btn) => {
    btn.addEventListener("click", () => removeVariationFactor(parseInt(btn.dataset.index, 10)));
  });
  list.querySelectorAll(".js-edit-variation-factor").forEach((btn) => {
    btn.addEventListener("click", () => startVaryingLayer(parseInt(btn.dataset.step, 10), btn.dataset.field));
  });
}

function variationRowHtml(row, index) {
  const entity = state.variationEntities[index] || { sample_id: "", location: "" };
  const cells = row.factorValues.map((v) => `<td class="mono sb-samples-table__num">${escapeHtml(formatParamValue(v))}</td>`).join("");
  return `
    <tr>
      <td class="sb-samples-table__idx mono">${index + 1}</td>
      <td><div class="variation-thumb">${row.svg}</div></td>
      ${cells}
      <td><input class="field js-wafer-name" data-index="${index}" value="${escapeHtml(entity.sample_id || "")}" placeholder="ex : W12-A3" aria-label="Nom du wafer, ligne ${index + 1}"></td>
      <td><input class="field js-wafer-location" data-index="${index}" value="${escapeHtml(entity.location || "")}" placeholder="optionnel" aria-label="Emplacement, ligne ${index + 1}"></td>
      <td class="sb-samples-table__fdl"><div class="js-wafer-fdl" data-index="${index}"></div></td>
    </tr>`;
}

function renderVariationTable(rows, factorLabels) {
  const wrap = document.getElementById("variation-table-wrap");
  if (state.variationEntities.length !== rows.length) {
    state.variationEntities = rows.map((_, i) => state.variationEntities[i] || { sample_id: "", location: "" });
  }
  const headerFactors = factorLabels
    .map((label, j) => {
      const factor = state.variationFactors[j];
      return `<th>${escapeHtml(label)}${factor && factor.scale === "log" ? ` <span class="sb-factor__scale sb-factor__scale--log">log</span>` : ""}</th>`;
    })
    .join("");
  wrap.innerHTML = `
    <table class="sb-samples-table">
      <thead>
        <tr>
          <th>#</th>
          <th>Aperçu</th>
          ${headerFactors}
          <th>Nom du wafer</th>
          <th>Emplacement</th>
          <th title="Feuilles de lancement JIRA - Entrée pour en empiler plusieurs">FDL</th>
        </tr>
      </thead>
      <tbody>${rows.map((row, i) => variationRowHtml(row, i)).join("")}</tbody>
    </table>`;
  wrap.querySelectorAll(".js-wafer-name").forEach((input) => {
    input.addEventListener("input", () => {
      const i = parseInt(input.dataset.index, 10);
      state.variationEntities[i] = { ...state.variationEntities[i], sample_id: input.value };
    });
  });
  wrap.querySelectorAll(".js-wafer-location").forEach((input) => {
    input.addEventListener("input", () => {
      const i = parseInt(input.dataset.index, 10);
      state.variationEntities[i] = { ...state.variationEntities[i], location: input.value };
    });
  });
  // FDL (feuilles de lancement JIRA) : plusieurs par wafer, empilées (mountFdlField, wafers/static/fdl.js)
  wrap.querySelectorAll(".js-wafer-fdl").forEach((el) => {
    const i = parseInt(el.dataset.index, 10);
    mountFdlField(el, {
      values: (state.variationEntities[i] || {}).fdl || [],
      compact: true,
      label: `FDL du wafer, ligne ${i + 1}`,
      onChange: (fdl) => {
        state.variationEntities[i] = { ...state.variationEntities[i], fdl };
      },
    });
  });
}

// Régénère le tableau depuis le plan courant - un appel serveur avec le plan complet s'il y a au
// moins un facteur (même endpoint que l'ancien campaign.js utilisait pour prévisualiser), sinon
// une seule ligne locale à partir de la dernière simulation (voir simulation.js/state.frames).
// Le libellé du bouton de lancement de l'écran 3 dépend de ce qu'on s'apprête à faire :
// campagne (au moins une variation), simple évolution, ou nouveau lancement sans variation.
function updateLaunchVariationsLabel() {
  const btn = document.getElementById("launch-btn-variations");
  // des variations définies mais refusées par le serveur : ne jamais lancer sans elles en silence
  btn.disabled = state.variationFactors.length > 0 && !state.campaignPlan;
  if (btn.disabled) {
    btn.textContent = "Corrigez les variations pour lancer";
  } else if (state.campaignPlan) {
    const n = state.variationEntities.length || 1;
    btn.textContent = `Lancer la campagne (${n} échantillon${n > 1 ? "s" : ""})`;
  } else if (evolveExperienceId) {
    btn.textContent = "Enregistrer les modifications";
  } else {
    btn.textContent = "Lancer le suivi de cette expérience";
  }
}

let variationTableSeq = 0; // une réponse plus ancienne (ajouts rapprochés) n'écrase jamais la plus récente

async function refreshVariationTable() {
  const seq = ++variationTableSeq;
  if (state.variationFactors.length === 0) {
    state.campaignPlan = null;
    const frame = state.frames && state.frames.length ? state.frames[state.frames.length - 1] : null;
    renderVariationTable([{ svg: frame ? frame.svg : "", factorValues: [] }], []);
    updateLaunchVariationsLabel();
    return;
  }
  const plan = {
    factors: state.variationFactors.map(({ step_index, field, values, scale, field_label }) => ({ step_index, field, values, scale: scale || "linear", label: field_label })),
  };
  try {
    const result = await structuresApi.previewCampaign({
      substrate: substrateSpec(),
      steps: state.steps,
      declared_params: declaredParamsPayload(state.steps),
      plan,
    });
    if (seq !== variationTableSeq) return;
    state.campaignPlan = plan;
    const rows = result.svgs.map((svg, i) => ({ svg, factorValues: result.factor_values[i] }));
    renderVariationTable(rows, result.factor_labels);
    updateLaunchVariationsLabel();
  } catch (err) {
    if (seq !== variationTableSeq) return;
    state.campaignPlan = null;
    document.getElementById("variation-table-wrap").innerHTML = `<div class="sb-samples__error">Variation impossible : ${escapeHtml(err.message || String(err))}</div>`;
    updateLaunchVariationsLabel();
  }
}

// Le tableau positionnel attendu par le payload de lancement (entities) - une entrée par ligne,
// vide (sample_id/location null) pour une ligne non encore remplie plutôt qu'omise, pour que
// l'index reste aligné avec les entités simulées côté serveur.
function variationTableEntities() {
  // un numéro de FDL encore en cours de frappe (sans Entrée) compte aussi
  document.querySelectorAll("#variation-table-wrap .fdl-field__input").forEach((input) => input.dispatchEvent(new Event("blur")));
  return state.variationEntities.map((e) => ({
    sample_id: (e.sample_id || "").trim() || null,
    location: (e.location || "").trim() || null,
    fdl: e.fdl || [],
  }));
}

// Invalidé chaque fois que la structure change (voir renderSteps() dans step-list.js) : les
// index d'étape référencés par les facteurs pourraient plus rien vouloir dire, donc on repart
// d'un plan vide plutôt que de risquer un facteur qui pointe sur la mauvaise étape.
function invalidateVariations() {
  const hadPlan = state.variationFactors.length > 0 || variationEditingStepIndex !== null;
  state.variationFactors = [];
  state.variationEntities = [];
  state.campaignPlan = null;
  variationEditingStepIndex = null;
  if (hadPlan && state.wizardScreen === "variations") {
    renderVariationInspector();
    renderVariationFactorsList();
    refreshVariationTable();
  }
}

function showWizardStepVariations() {
  variationEditingStepIndex = null;
  // Report l'entité éventuellement saisie sur l'écran 2 (cas évolution) dans la 1re ligne du
  // tableau, pour ne pas la reperdre en basculant d'écran.
  const screenOneSampleId = (document.getElementById("exp-entity-sample-id").value || "").trim();
  if (screenOneSampleId && !(state.variationEntities[0] && state.variationEntities[0].sample_id)) {
    state.variationEntities[0] = {
      sample_id: screenOneSampleId,
      location: (document.getElementById("exp-entity-location").value || "").trim(),
      fdl: entityFdlField ? entityFdlField.get() : [],
    };
  }
  setStage("variations");
  renderVariationFactorsList();
  refreshVariationTable();
}

function showWizardStepIntention() {
  variationEditingStepIndex = null;
  setStage("intention");
}

document.getElementById("back-to-intention-btn").addEventListener("click", showWizardStepIntention);
