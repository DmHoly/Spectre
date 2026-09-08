/* Écran 2 (variations et échantillons) : cliquer une couche (ou une étape dans la liste) pour
   choisir un paramètre à faire varier - en linéaire (min/max/nombre de points) ou en valeurs
   précises (liste séparée par des virgules) - puis un tableau façon Excel, une ligne par
   combinaison, avec les noms de wafers et emplacements des échantillons réels. Sans variation,
   le tableau dégénère naturellement à une seule ligne (la structure telle quelle). Remplace
   l'ancien campaign.js (menus déroulants dans un accordéon) ; reprend la même forme de plan
   ({factors: [{step_index, field, values}]}) que preview_campaign/launch_campaign attendent déjà
   côté serveur, donc state.campaignPlan (lu par experience-launch.js) n'a pas changé de forme. */

let variationEditingStepIndex = null; // index de l'étape dont le panneau de droite montre le formulaire de variation
// Contenu original de #context-panel-empty (écran 1), capturé avant que showWizardStepVariations
// ne le remplace par son propre message - pour le restaurer tel quel au retour à l'écran 1.
const structureContextPanelEmptyHtml = document.getElementById("context-panel-empty").innerHTML;

function variationFieldOptionsHtml(stepIndex) {
  const step = state.steps[stepIndex];
  const options = step ? CAMPAIGN_FIELD_OPTIONS[step.kind] || [] : [];
  const optionsHtml = options.map(([value, label]) => `<option value="${value}">${label}</option>`);
  return optionsHtml.length ? optionsHtml.join("") : `<option value="">Aucun paramètre modifiable sur cette étape</option>`;
}

function setVariationMode(mode) {
  document.getElementById("variation-mode-linear").classList.toggle("active", mode === "linear");
  document.getElementById("variation-mode-explicit").classList.toggle("active", mode === "explicit");
  document.getElementById("variation-linear-fields").style.display = mode === "linear" ? "" : "none";
  document.getElementById("variation-explicit-fields").style.display = mode === "explicit" ? "" : "none";
}

document.getElementById("variation-mode-linear").addEventListener("click", () => setVariationMode("linear"));
document.getElementById("variation-mode-explicit").addEventListener("click", () => setVariationMode("explicit"));

// Point d'entrée commun au clic sur une couche du dessin et au clic sur une étape de la liste
// (voir step-list.js) - ouvre le formulaire de variation pour cette étape dans #context-panel,
// à la place du formulaire d'ajout/édition d'étape utilisé à l'écran 1.
function startVaryingLayer(stepIndex) {
  const step = state.steps[stepIndex];
  if (!step || (CAMPAIGN_FIELD_OPTIONS[step.kind] || []).length === 0) return;
  variationEditingStepIndex = stepIndex;
  document.getElementById("context-panel-empty").style.display = "none";
  document.getElementById("step-form-section").style.display = "none";
  document.getElementById("variation-form-section").style.display = "";
  document.getElementById("variation-form-title").textContent = `Variation — ${step.name} (étape ${stepIndex + 1})`;
  document.getElementById("variation-field-select").innerHTML = variationFieldOptionsHtml(stepIndex);
  document.getElementById("variation-min").value = "";
  document.getElementById("variation-max").value = "";
  document.getElementById("variation-count").value = "3";
  document.getElementById("variation-values").value = "";
  setVariationMode("linear");
  highlightVariationLayer();
}

function cancelVaryingLayer() {
  variationEditingStepIndex = null;
  document.getElementById("variation-form-section").style.display = "none";
  document.getElementById("context-panel-empty").style.display = "";
  highlightVariationLayer();
}

document.getElementById("cancel-variation-btn").addEventListener("click", cancelVaryingLayer);

function linearValues(min, max, count) {
  if (!Number.isFinite(min) || !Number.isFinite(max) || !Number.isInteger(count) || count < 2) return [];
  const step = (max - min) / (count - 1);
  return Array.from({ length: count }, (_, i) => Math.round((min + step * i) * 1e6) / 1e6);
}

document.getElementById("add-variation-btn").addEventListener("click", () => {
  clearError();
  if (variationEditingStepIndex === null) return;
  const stepIndex = variationEditingStepIndex;
  const select = document.getElementById("variation-field-select");
  const field = select.value;
  const fieldLabel = select.options[select.selectedIndex] ? select.options[select.selectedIndex].textContent : field;
  if (!field) {
    showError(new Error("Choisissez un paramètre à faire varier."));
    return;
  }
  const linearMode = document.getElementById("variation-mode-linear").classList.contains("active");
  let values;
  if (linearMode) {
    const min = parseFloat(document.getElementById("variation-min").value);
    const max = parseFloat(document.getElementById("variation-max").value);
    const count = parseInt(document.getElementById("variation-count").value, 10);
    values = linearValues(min, max, count);
    if (values.length === 0) {
      showError(new Error("Renseignez un minimum, un maximum et au moins 2 points."));
      return;
    }
  } else {
    values = document
      .getElementById("variation-values")
      .value.split(",")
      .map((v) => parseFloat(v.trim()))
      .filter((v) => !Number.isNaN(v));
    if (values.length === 0) {
      showError(new Error("Renseignez au moins une valeur."));
      return;
    }
  }
  state.variationFactors = state.variationFactors.filter((f) => !(f.step_index === stepIndex && f.field === field));
  state.variationFactors.push({ step_index: stepIndex, field, field_label: `${fieldLabel} — ${state.steps[stepIndex].name}`, values });
  cancelVaryingLayer();
  renderVariationFactorsList();
  refreshVariationTable();
});

function removeVariationFactor(index) {
  state.variationFactors.splice(index, 1);
  renderVariationFactorsList();
  refreshVariationTable();
}

function renderVariationFactorsList() {
  const list = document.getElementById("variation-factors-list");
  if (state.variationFactors.length === 0) {
    list.innerHTML = `<div class="help">Aucune variation définie : un seul échantillon sera lancé, tel quel.</div>`;
    return;
  }
  list.innerHTML = state.variationFactors
    .map(
      (f, i) => `
      <div class="step-row" style="align-items:flex-start;">
        <div style="flex:1;min-width:0;">
          <div style="font-size:13px;font-weight:600;">${escapeHtml(f.field_label)}</div>
          <div style="font-size:12px;color:var(--text-faint);">${f.values.join(", ")}</div>
        </div>
        <button class="step-remove js-remove-variation-factor" data-index="${i}" type="button">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 5l14 14M5 19L19 5"/></svg>
        </button>
      </div>`
    )
    .join("");
  list.querySelectorAll(".js-remove-variation-factor").forEach((btn) => {
    btn.addEventListener("click", () => removeVariationFactor(parseInt(btn.dataset.index, 10)));
  });
}

function highlightVariationLayer() {
  const container = document.getElementById("svg-container");
  container.querySelectorAll("[data-layer-index]").forEach((path) => {
    const stepIndex = parseInt(path.dataset.layerIndex, 10) - 1;
    const selected = state.wizardScreen === "variations" && variationEditingStepIndex === stepIndex;
    path.style.stroke = selected ? "var(--accent)" : "";
    path.style.strokeWidth = selected ? "2.5" : "";
  });
}

function variationRowHtml(row, index) {
  const entity = state.variationEntities[index] || { sample_id: "", location: "" };
  const cells = row.factorValues.map((v) => `<td class="mono" style="padding:6px 10px;white-space:nowrap;">${v}</td>`).join("");
  return `
    <tr>
      <td style="padding:6px 10px;"><div class="variation-thumb">${row.svg}</div></td>
      ${cells}
      <td style="padding:6px 10px;"><input class="field js-wafer-name" data-index="${index}" value="${escapeHtml(entity.sample_id || "")}" placeholder="ex : W12-A3" style="min-width:110px;"></td>
      <td style="padding:6px 10px;"><input class="field js-wafer-location" data-index="${index}" value="${escapeHtml(entity.location || "")}" placeholder="optionnel" style="min-width:110px;"></td>
    </tr>`;
}

function renderVariationTable(rows, factorLabels) {
  const wrap = document.getElementById("variation-table-wrap");
  if (state.variationEntities.length !== rows.length) {
    state.variationEntities = rows.map((_, i) => state.variationEntities[i] || { sample_id: "", location: "" });
  }
  const headerFactors = factorLabels.map((label) => `<th style="padding:6px 10px;text-align:left;font-size:11.5px;color:var(--text-soft);">${escapeHtml(label)}</th>`).join("");
  wrap.innerHTML = `
    <table style="border-collapse:collapse;width:100%;font-size:12.5px;">
      <thead>
        <tr style="border-bottom:1px solid var(--border-soft);">
          <th style="padding:6px 10px;text-align:left;font-size:11.5px;color:var(--text-soft);">Aperçu</th>
          ${headerFactors}
          <th style="padding:6px 10px;text-align:left;font-size:11.5px;color:var(--text-soft);">Nom du wafer</th>
          <th style="padding:6px 10px;text-align:left;font-size:11.5px;color:var(--text-soft);">Emplacement</th>
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
}

// Régénère le tableau depuis le plan courant - un appel serveur avec le plan complet s'il y a au
// moins un facteur (même endpoint que l'ancien campaign.js utilisait pour prévisualiser), sinon
// une seule ligne locale à partir de la dernière simulation (voir simulation.js/state.frames).
// Le libellé du bouton de lancement de l'écran 2 dépend de ce qu'on s'apprête à faire :
// campagne (au moins une variation), simple évolution, ou nouveau lancement sans variation.
function updateLaunchVariationsLabel() {
  const btn = document.getElementById("launch-btn-variations");
  if (state.campaignPlan) {
    const n = state.variationEntities.length || 1;
    btn.textContent = `Lancer la campagne (${n} échantillon${n > 1 ? "s" : ""})`;
  } else if (evolveExperienceId) {
    btn.textContent = "Enregistrer cette évolution";
  } else {
    btn.textContent = "Lancer le suivi de cette expérience";
  }
}

async function refreshVariationTable() {
  if (state.variationFactors.length === 0) {
    state.campaignPlan = null;
    const frame = state.frames && state.frames.length ? state.frames[state.frames.length - 1] : null;
    renderVariationTable([{ svg: frame ? frame.svg : "", factorValues: [] }], []);
    updateLaunchVariationsLabel();
    return;
  }
  const plan = { factors: state.variationFactors.map(({ step_index, field, values }) => ({ step_index, field, values })) };
  try {
    const result = await api.post(`/api/microprojets/${slug}/structures/variantes`, {
      substrate: substrateSpec(),
      steps: state.steps,
      plan,
    });
    state.campaignPlan = plan;
    const rows = result.svgs.map((svg, i) => ({ svg, factorValues: result.factor_values[i] }));
    renderVariationTable(rows, result.factor_labels);
    updateLaunchVariationsLabel();
  } catch (err) {
    showError(err);
  }
}

// Le tableau positionnel attendu par le payload de lancement (entities) - une entrée par ligne,
// vide (sample_id/location null) pour une ligne non encore remplie plutôt qu'omise, pour que
// l'index reste aligné avec les entités simulées côté serveur.
function variationTableEntities() {
  return state.variationEntities.map((e) => ({
    sample_id: (e.sample_id || "").trim() || null,
    location: (e.location || "").trim() || null,
  }));
}

// Invalidé chaque fois que la structure change (voir renderSteps() dans step-list.js) : les
// index d'étape référencés par les facteurs pourraient plus rien vouloir dire, donc on repart
// d'un plan vide plutôt que de risquer un facteur qui pointe sur la mauvaise étape.
function invalidateVariations() {
  state.variationFactors = [];
  state.variationEntities = [];
  state.campaignPlan = null;
  variationEditingStepIndex = null;
  if (document.getElementById("variation-form-section")) {
    document.getElementById("variation-form-section").style.display = "none";
  }
  if (state.wizardScreen === "variations") {
    document.getElementById("context-panel-empty").style.display = "";
    renderVariationFactorsList();
    refreshVariationTable();
  }
}

function showWizardStepVariations() {
  state.wizardScreen = "variations";
  variationEditingStepIndex = null;
  // Report l'entité éventuellement saisie sur l'écran 1 (cas évolution) dans la 1re ligne du
  // tableau, pour ne pas la reperdre en basculant d'écran.
  const screenOneSampleId = (document.getElementById("exp-entity-sample-id").value || "").trim();
  if (screenOneSampleId && !(state.variationEntities[0] && state.variationEntities[0].sample_id)) {
    state.variationEntities[0] = {
      sample_id: screenOneSampleId,
      location: (document.getElementById("exp-entity-location").value || "").trim(),
    };
  }
  document.getElementById("variation-form-section").style.display = "none";
  document.getElementById("wizard-step-intention").style.display = "none";
  document.getElementById("wizard-step-variations").style.display = "flex";
  document.getElementById("context-panel-empty").innerHTML = `
    <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 19V9l8-5 8 5v10"/><path d="M9 19v-6h6v6"/></svg>
    <p>Cliquez une couche du dessin, ou une étape dans la liste, pour choisir un paramètre à faire varier.</p>`;
  document.getElementById("context-panel-empty").style.display = "";
  document.getElementById("step-form-section").style.display = "none";
  renderVariationFactorsList();
  refreshVariationTable();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function showWizardStepIntention() {
  state.wizardScreen = "intention";
  variationEditingStepIndex = null;
  document.getElementById("variation-form-section").style.display = "none";
  document.getElementById("context-panel-empty").innerHTML = structureContextPanelEmptyHtml;
  document.getElementById("wizard-step-variations").style.display = "none";
  document.getElementById("wizard-step-intention").style.display = "flex";
  updateStepFormVisibility();
  highlightSelectedLayer();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

document.getElementById("back-to-intention-btn").addEventListener("click", showWizardStepIntention);
