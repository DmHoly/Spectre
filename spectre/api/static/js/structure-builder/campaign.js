/* Campagne DOE : choix des paramètres à faire varier (un ou plusieurs) et de leurs valeurs,
   prévisualisation via l'API avant de lancer le suivi. */

function campaignStepOptionsHtml() {
  if (state.steps.length === 0) return `<option value="">Ajoutez au moins une étape d'abord</option>`;
  return state.steps
    .map((s, i) => `<option value="${i}">${i + 1}. ${escapeHtml(STEP_KINDS[s.kind].label)} — ${escapeHtml(s.name)}</option>`)
    .join("");
}

function campaignFieldOptionsHtml(stepIndex) {
  const step = state.steps[stepIndex];
  const options = step ? CAMPAIGN_FIELD_OPTIONS[step.kind] || [] : [];
  const estimateOptions = step && step.derived_estimates ? step.derived_estimates : [];
  const optionsHtml = options.map(([value, label]) => `<option value="${value}">${label}</option>`);
  // a derived estimate (ex : dopage) is split by choosing target estimate values directly - the
  // step's process parameter is solved from them server-side (see _step_with_estimate_value).
  const estimateOptionsHtml = estimateOptions.map(
    (e) => `<option value="estimate:${escapeHtml(e.name)}">${escapeHtml(e.name)} (estimée)</option>`
  );
  const all = [...optionsHtml, ...estimateOptionsHtml];
  return all.length ? all.join("") : `<option value="">Aucun paramètre modifiable sur cette étape</option>`;
}

function addCampaignFactorRow() {
  const row = document.createElement("div");
  row.className = "js-campaign-factor-row";
  row.style = "border:1px solid var(--border-soft);border-radius:8px;padding:10px;display:flex;flex-direction:column;gap:8px;";
  row.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;">
      <label style="margin:0;">Étape</label>
      <button class="js-remove-factor" type="button" style="background:none;border:none;cursor:pointer;color:var(--text-faint);font-size:14px;line-height:1;">&times;</button>
    </div>
    <select class="field js-factor-step">${campaignStepOptionsHtml()}</select>
    <label>Paramètre</label>
    <select class="field js-factor-field"></select>
    <label>Valeurs</label>
    <input class="field js-factor-values" placeholder="ex : 10, 20, 30">`;
  document.getElementById("campaign-factors").appendChild(row);
  const stepSelect = row.querySelector(".js-factor-step");
  const fieldSelect = row.querySelector(".js-factor-field");
  const refreshField = () => {
    fieldSelect.innerHTML = campaignFieldOptionsHtml(parseInt(stepSelect.value, 10));
  };
  stepSelect.addEventListener("change", refreshField);
  refreshField();
  row.querySelector(".js-remove-factor").addEventListener("click", () => row.remove());
}

document.getElementById("campaign-add-factor-btn").addEventListener("click", addCampaignFactorRow);

function refreshCampaignFactorSteps() {
  document.querySelectorAll(".js-campaign-factor-row").forEach((row) => {
    const stepSelect = row.querySelector(".js-factor-step");
    const previous = stepSelect.value;
    stepSelect.innerHTML = campaignStepOptionsHtml();
    stepSelect.value = [...stepSelect.options].some((o) => o.value === previous) ? previous : stepSelect.value;
    row.querySelector(".js-factor-field").innerHTML = campaignFieldOptionsHtml(parseInt(stepSelect.value, 10));
  });
}

function campaignPlan() {
  const rows = [...document.querySelectorAll(".js-campaign-factor-row")];
  if (rows.length === 0) return null;
  const factors = [];
  for (const row of rows) {
    const stepIndex = parseInt(row.querySelector(".js-factor-step").value, 10);
    const fieldValue = row.querySelector(".js-factor-field").value;
    const values = row
      .querySelector(".js-factor-values")
      .value.split(",")
      .map((v) => parseFloat(v.trim()))
      .filter((v) => !Number.isNaN(v));
    if (Number.isNaN(stepIndex) || !fieldValue || values.length === 0) return null;
    if (fieldValue.startsWith("estimate:")) {
      factors.push({ step_index: stepIndex, via_estimate: fieldValue.slice("estimate:".length), values });
    } else {
      factors.push({ step_index: stepIndex, field: fieldValue, values });
    }
  }
  return { factors };
}

document.getElementById("campaign-preview-btn").addEventListener("click", async () => {
  clearError();
  const plan = campaignPlan();
  if (!plan) {
    showError(new Error("Pour chaque paramètre : choisissez une étape, un paramètre et au moins une valeur."));
    return;
  }
  try {
    const result = await api.post(`/api/projects/${slug}/structures/variantes`, {
      substrate: substrateSpec(),
      steps: state.steps,
      plan,
    });
    state.campaignPlan = plan;
    const variation = result.variation;
    document.getElementById("campaign-result").innerHTML = `
      <div style="font-size:12.5px;color:var(--text-soft);margin-top:10px;">
        ${variation.entity_count} échantillons &middot; ${result.factor_labels.join(" &times; ")}
      </div>
      <div style="display:flex;gap:8px;margin-top:8px;overflow-x:auto;">
        ${result.svgs.map((svg, i) => `<div style="flex:none;width:120px;border:1px solid var(--border-soft);border-radius:6px;padding:4px;text-align:center;">${svg}<div class="mono" style="font-size:11px;color:var(--text-soft);margin-top:4px;">${escapeHtml(result.labels[i])}</div></div>`).join("")}
      </div>`;
  } catch (err) {
    showError(err);
  }
});

document.getElementById("campaign-clear-btn").addEventListener("click", () => {
  state.campaignPlan = null;
  document.getElementById("campaign-factors").innerHTML = "";
  document.getElementById("campaign-result").innerHTML = "";
  addCampaignFactorRow();
});
