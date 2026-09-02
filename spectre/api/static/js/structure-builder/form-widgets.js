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

function wireModeAngleToggle(kind) {
  const modeSelect = document.getElementById("f-mode");
  const angleWrap = document.getElementById("f-angle-wrap");
  const update = () => {
    angleWrap.style.display = modeSelect.value === "directional" ? "" : "none";
  };
  modeSelect.addEventListener("change", update);
  update();
  document.getElementById("f-preset").addEventListener("change", (e) => {
    const value = e.target.value;
    if (!value) return;
    const [scope, name] = value.split("::");
    const preset = findStepPreset(scope, decodeURIComponent(name));
    if (!preset) return;
    modeSelect.value = preset.payload.mode;
    document.getElementById("f-angle").value = preset.payload.angle_deg || 0;
    update();
    if (kind === "etch") {
      document.getElementById("f-default-factor").value = preset.payload.default_factor != null ? preset.payload.default_factor : 1.0;
      document.getElementById("f-selectivity-rows").innerHTML = "";
      Object.entries(preset.payload.selectivity_by_material || {}).forEach(([material, factor]) => addSelectivityRow(material, factor));
    }
  });
}

function addSelectivityRow(material, factor) {
  const row = document.createElement("div");
  row.className = "field-row js-selectivity-row";
  row.style.gridTemplateColumns = "1fr 100px auto";
  row.innerHTML = `
    <select class="field js-sel-material">${materialOptions(material)}</select>
    <input class="field js-sel-factor" type="number" step="0.01" min="0" placeholder="facteur" value="${factor != null ? factor : ""}">
    <button class="js-sel-remove" type="button" style="background:none;border:none;cursor:pointer;color:var(--text-faint);font-size:14px;">&times;</button>`;
  document.getElementById("f-selectivity-rows").appendChild(row);
  row.querySelector(".js-sel-remove").addEventListener("click", () => row.remove());
}

function currentSelectivityByMaterial() {
  const out = {};
  document.querySelectorAll("#f-selectivity-rows .js-selectivity-row").forEach((row) => {
    const material = row.querySelector(".js-sel-material").value;
    const factor = parseFloat(row.querySelector(".js-sel-factor").value);
    if (material && !Number.isNaN(factor)) out[material] = factor;
  });
  return out;
}

function wireSelectiveGrowthRateCheck() {
  const check = () => {
    const rateM = parseFloat(document.getElementById("f-rate-m").value);
    const rateSp = parseFloat(document.getElementById("f-rate-sp").value);
    const hint = document.getElementById("f-rate-order-hint");
    const ok = rateSp > 0 && rateM > rateSp && rateM < 1.0;
    hint.style.color = ok ? "" : "var(--danger)";
  };
  document.getElementById("f-rate-m").addEventListener("input", check);
  document.getElementById("f-rate-sp").addEventListener("input", check);
  check();
}

function currentProcessParameters() {
  const params = {};
  document.querySelectorAll(".js-process-param-row").forEach((row) => {
    const name = row.querySelector(".js-pp-name").value.trim();
    const value = parseFloat(row.querySelector(".js-pp-value").value);
    if (name && !Number.isNaN(value)) params[name] = value;
  });
  return params;
}

function currentDerivedEstimates() {
  return [...document.querySelectorAll(".js-estimate-row")]
    .map((row) => ({
      name: row.querySelector(".js-est-name").value.trim(),
      parameter: row.querySelector(".js-est-parameter").value,
      coefficient: parseFloat(row.querySelector(".js-est-coefficient").value),
      offset: parseFloat(row.querySelector(".js-est-offset").value) || 0,
      unit: row.querySelector(".js-est-unit").value.trim() || null,
    }))
    .filter((e) => e.name && e.parameter && !Number.isNaN(e.coefficient));
}

function refreshEstimateParameterOptions() {
  const names = [...document.querySelectorAll(".js-pp-name")].map((el) => el.value.trim()).filter(Boolean);
  document.querySelectorAll(".js-est-parameter").forEach((select) => {
    const previous = select.value;
    select.innerHTML = names.length
      ? names.map((n) => `<option value="${escapeHtml(n)}">${escapeHtml(n)}</option>`).join("")
      : `<option value="">Ajoutez un paramètre process d'abord</option>`;
    if (names.includes(previous)) select.value = previous;
  });
  updateEstimatePreviews();
}

function updateEstimatePreviews() {
  const params = currentProcessParameters();
  document.querySelectorAll(".js-estimate-row").forEach((row) => {
    const parameter = row.querySelector(".js-est-parameter").value;
    const coefficient = parseFloat(row.querySelector(".js-est-coefficient").value);
    const offset = parseFloat(row.querySelector(".js-est-offset").value) || 0;
    const unit = row.querySelector(".js-est-unit").value.trim();
    const preview = row.querySelector(".js-est-preview");
    if (parameter && parameter in params && !Number.isNaN(coefficient)) {
      const value = offset + coefficient * params[parameter];
      preview.textContent = `≈ ${value}${unit ? " " + unit : ""}`;
    } else {
      preview.textContent = "";
    }
  });
}

function addProcessParamRow(name, value) {
  const row = document.createElement("div");
  row.className = "field-row js-process-param-row";
  row.style.gridTemplateColumns = "1fr 100px auto";
  row.innerHTML = `
    <input class="field js-pp-name" placeholder="nom (ex : flux)" value="${escapeHtml(name || "")}">
    <input class="field js-pp-value" type="number" step="any" placeholder="valeur" value="${value != null ? value : ""}">
    <button class="js-pp-remove" type="button" style="background:none;border:none;cursor:pointer;color:var(--text-faint);font-size:14px;">&times;</button>`;
  document.getElementById("f-process-params-rows").appendChild(row);
  row.querySelector(".js-pp-name").addEventListener("input", refreshEstimateParameterOptions);
  row.querySelector(".js-pp-value").addEventListener("input", updateEstimatePreviews);
  row.querySelector(".js-pp-remove").addEventListener("click", () => {
    row.remove();
    refreshEstimateParameterOptions();
  });
}

function addEstimateRow(estimate) {
  estimate = estimate || {};
  const row = document.createElement("div");
  row.className = "js-estimate-row";
  row.style = "border:1px solid var(--border-soft);border-radius:8px;padding:8px;display:flex;flex-direction:column;gap:6px;";
  row.innerHTML = `
    <div style="display:flex;justify-content:space-between;gap:6px;">
      <input class="field js-est-name" placeholder="nom (ex : dopage)" style="flex:1;" value="${escapeHtml(estimate.name || "")}">
      <button class="js-est-remove" type="button" style="background:none;border:none;cursor:pointer;color:var(--text-faint);font-size:14px;">&times;</button>
    </div>
    <select class="field js-est-parameter"></select>
    <div class="field-row">
      <input class="field js-est-coefficient" type="number" step="any" value="${estimate.coefficient != null ? estimate.coefficient : 1}" placeholder="coefficient">
      <input class="field js-est-offset" type="number" step="any" value="${estimate.offset != null ? estimate.offset : 0}" placeholder="décalage">
    </div>
    <input class="field js-est-unit" placeholder="unité (optionnel)" value="${escapeHtml(estimate.unit || "")}">
    <div class="js-est-preview" style="font-size:11.5px;color:var(--text-faint);"></div>`;
  document.getElementById("f-estimates-rows").appendChild(row);
  row.querySelectorAll("input").forEach((input) => input.addEventListener("input", updateEstimatePreviews));
  row.querySelector(".js-est-remove").addEventListener("click", () => row.remove());
  refreshEstimateParameterOptions();
  if (estimate.parameter) row.querySelector(".js-est-parameter").value = estimate.parameter;
  updateEstimatePreviews();
}

function wireDepositionAdvanced() {
  document.getElementById("f-add-process-param-btn").addEventListener("click", () => addProcessParamRow());
  document.getElementById("f-add-estimate-btn").addEventListener("click", () => addEstimateRow());
}

function parseOpenings(text) {
  if (!text.trim()) return [];
  return text.split(",").map((part) => {
    const [a, b] = part.split("-").map((n) => parseFloat(n.trim()));
    return [a, b];
  });
}

const MODE_LABELS = { conformal: "conforme", directional: "directionnel", isotropic: "isotrope", anisotropic: "anisotrope" };

function modeSummary(mode, angle_deg) {
  const label = MODE_LABELS[mode] || mode;
  return angle_deg ? `${label} (${angle_deg}°)` : label;
}
