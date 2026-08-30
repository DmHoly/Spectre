/* Constructeur de structure : formulaire de substrat + étapes de procédé, aperçu simulé
   (StructureForge fait tout le calcul et dessine le SVG - cette page ne fait qu'assembler la
   requête et afficher ce qui revient), puis lancement du suivi ou enregistrement d'une évolution. */

const STEP_KINDS = {
  deposition: { label: "Dépôt", icon: "deposition", color: "#1d6fae", tint: "#e8f1fa" },
  etch: { label: "Gravure", icon: "etch", color: "#a45a3a", tint: "#f6ede7" },
  planarization: { label: "Planarisation", icon: "planarization", color: "#5c655e", tint: "#ede9df" },
  lithography: { label: "Lithographie", icon: "lithography", color: "#7a4a97", tint: "#f2e9f7" },
  chemical: { label: "Étape chimique", icon: "chemical", color: "#3f7d4a", tint: "#e9f4ea" },
  resist_strip: { label: "Retrait de résine", icon: "resist_strip", color: "#a45a3a", tint: "#f6ede7" },
};

const STEP_ICON_PATHS = {
  deposition: '<path d="M12 3v13m0 0l-5-5m5 5l5-5M4 20h16"/>',
  etch: '<path d="M12 21V8m0 0l-5 5m5-5l5 5M4 4h16"/>',
  planarization: '<path d="M4 12h16M8 6h8M8 18h8"/>',
  lithography: '<path d="M6 4l12 16M18 4L6 20"/>',
  chemical: '<path d="M9 3h6M10 3v5l-5 9a2 2 0 002 3h10a2 2 0 002-3l-5-9V3"/>',
  resist_strip: '<path d="M5 5l14 14M5 19L19 5"/>',
};

function stepIconHtml(kind) {
  const info = STEP_KINDS[kind];
  return `
    <div class="step-icon" style="background:${info.tint};color:${info.color};">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">${STEP_ICON_PATHS[kind]}</svg>
    </div>`;
}

const pathParts = window.location.pathname.split("/").filter(Boolean);
const slug = pathParts[1];
const evolveExperienceId = pathParts[2] === "experiences" ? pathParts[3] : null;
const templateExperienceId = evolveExperienceId ? null : new URLSearchParams(window.location.search).get("depuis");

const state = {
  materials: [],
  recipes: { deposition: [], etch: [] },
  steps: [],
  objectives: [],
  frames: null,
  materialColors: {},
  currentFrame: 0,
  campaignPlan: null,
  editingIndex: null,
};

const errorBox = document.getElementById("error");
function showError(err) {
  errorBox.textContent = err.message || String(err);
  errorBox.style.display = "block";
}
function clearError() {
  errorBox.style.display = "none";
}

function lengthValue(id) {
  return { value: parseFloat(document.getElementById(id).value) || 0, unit: document.getElementById(id + "-unit").value };
}

function materialOptions(selectedValue) {
  return state.materials
    .map((m) => `<option value="${escapeHtml(m.name)}" ${m.name === selectedValue ? "selected" : ""}>${escapeHtml(m.name)}</option>`)
    .join("");
}

function recipeOptions(kind, selectedValue) {
  return state.recipes[kind]
    .map((r) => `<option value="${escapeHtml(r.name)}" ${r.name === selectedValue ? "selected" : ""}>${escapeHtml(r.name)}</option>`)
    .join("");
}

function renderKindFields(kind) {
  const container = document.getElementById("kind-fields");
  if (kind === "deposition") {
    container.innerHTML = `
      <div><label>Nom de l'étape</label><input class="field" id="f-name" value="Dépôt"></div>
      <div><label>Matériau</label><select class="field" id="f-material">${materialOptions()}</select></div>
      <div><label>Recette</label><select class="field" id="f-recipe">${recipeOptions("deposition")}</select></div>
      <div class="field-row"><div><label>Épaisseur</label><input class="field" id="f-thickness" type="number" value="20"></div>
      <div><label>Unité</label><select class="field" id="f-thickness-unit"><option value="nm" selected>nm</option><option value="um">µm</option><option value="A">Å</option></select></div></div>`;
  } else if (kind === "etch") {
    container.innerHTML = `
      <div><label>Nom de l'étape</label><input class="field" id="f-name" value="Gravure"></div>
      <div><label>Recette</label><select class="field" id="f-recipe">${recipeOptions("etch")}</select></div>
      <div class="field-row"><div><label>Profondeur</label><input class="field" id="f-depth" type="number" value="10"></div>
      <div><label>Unité</label><select class="field" id="f-depth-unit"><option value="nm" selected>nm</option><option value="um">µm</option><option value="A">Å</option></select></div></div>`;
  } else if (kind === "planarization") {
    container.innerHTML = `
      <div><label>Nom de l'étape</label><input class="field" id="f-name" value="Planarisation"></div>
      <div><label>S'arrête sur</label>
        <select class="field" id="f-plana-mode"><option value="level">Un niveau précis</option><option value="material">Un matériau</option></select>
      </div>
      <div id="f-plana-value"><div class="field-row"><div><input class="field" id="f-target-level" type="number" value="0"></div><div><select class="field" id="f-target-level-unit"><option value="nm" selected>nm</option><option value="um">µm</option></select></div></div></div>`;
    document.getElementById("f-plana-mode").addEventListener("change", (e) => {
      const target = document.getElementById("f-plana-value");
      target.innerHTML =
        e.target.value === "level"
          ? `<div class="field-row"><div><input class="field" id="f-target-level" type="number" value="0"></div><div><select class="field" id="f-target-level-unit"><option value="nm" selected>nm</option><option value="um">µm</option></select></div></div>`
          : `<select class="field" id="f-stop-material">${materialOptions()}</select>`;
    });
  } else if (kind === "lithography") {
    container.innerHTML = `
      <div><label>Nom de l'étape</label><input class="field" id="f-name" value="Lithographie"></div>
      <div><label>Résine</label><select class="field" id="f-resist-material">${materialOptions("Photoresist")}</select></div>
      <div class="field-row"><div><label>Épaisseur</label><input class="field" id="f-thickness" type="number" value="500"></div>
      <div><label>Unité</label><select class="field" id="f-thickness-unit"><option value="nm" selected>nm</option></select></div></div>
      <div><label>Ouvertures (nm)</label><input class="field" id="f-openings" placeholder="ex : 80-140, 300-360"><div class="help">Zones où le masque est ouvert, séparées par des virgules.</div></div>`;
  } else if (kind === "chemical") {
    container.innerHTML = `
      <div><label>Nom de l'étape</label><input class="field" id="f-name" value="Nettoyage"></div>
      <div><label>Description (optionnelle)</label><input class="field" id="f-description" placeholder="ex : bain HF"></div>`;
  } else if (kind === "resist_strip") {
    container.innerHTML = `
      <div><label>Nom de l'étape</label><input class="field" id="f-name" value="Retrait de résine"></div>
      <div><label>Matériau</label><select class="field" id="f-material">${materialOptions("Photoresist")}</select></div>`;
  }
}

function parseOpenings(text) {
  if (!text.trim()) return [];
  return text.split(",").map((part) => {
    const [a, b] = part.split("-").map((n) => parseFloat(n.trim()));
    return [a, b];
  });
}

function buildStepFromForm() {
  const kind = document.getElementById("kind-select").value;
  const name = document.getElementById("f-name").value || STEP_KINDS[kind].label;
  if (kind === "deposition") {
    return {
      kind,
      name,
      material: document.getElementById("f-material").value,
      recipe: document.getElementById("f-recipe").value,
      thickness: { value: parseFloat(document.getElementById("f-thickness").value) || 0, unit: document.getElementById("f-thickness-unit").value },
    };
  }
  if (kind === "etch") {
    return {
      kind,
      name,
      recipe: document.getElementById("f-recipe").value,
      depth: { value: parseFloat(document.getElementById("f-depth").value) || 0, unit: document.getElementById("f-depth-unit").value },
    };
  }
  if (kind === "planarization") {
    const mode = document.getElementById("f-plana-mode").value;
    if (mode === "level") {
      return {
        kind,
        name,
        target_level: { value: parseFloat(document.getElementById("f-target-level").value) || 0, unit: document.getElementById("f-target-level-unit").value },
      };
    }
    return { kind, name, stop_material: document.getElementById("f-stop-material").value };
  }
  if (kind === "lithography") {
    return {
      kind,
      name,
      resist_material: document.getElementById("f-resist-material").value,
      thickness: { value: parseFloat(document.getElementById("f-thickness").value) || 0, unit: document.getElementById("f-thickness-unit").value },
      openings: parseOpenings(document.getElementById("f-openings").value),
    };
  }
  if (kind === "chemical") {
    return { kind, name, description: document.getElementById("f-description").value || null, parameters: {} };
  }
  return { kind, name, material: document.getElementById("f-material").value };
}

function stepSummary(step) {
  if (step.kind === "deposition") return `${step.material} · ${step.thickness.value} ${step.thickness.unit} · ${step.recipe}`;
  if (step.kind === "etch") return `${step.recipe} · ${step.depth.value} ${step.depth.unit}`;
  if (step.kind === "planarization") return step.target_level ? `jusqu'à ${step.target_level.value} ${step.target_level.unit}` : `jusqu'au ${step.stop_material}`;
  if (step.kind === "lithography") return `${step.resist_material} · ${step.openings.length} ouverture(s)`;
  if (step.kind === "chemical") return step.description || "sans effet géométrique";
  return step.material;
}

function renderSteps() {
  const list = document.getElementById("steps-list");
  document.getElementById("steps-count").textContent = state.steps.length;
  if (state.steps.length === 0) {
    list.innerHTML = `<div class="help" style="padding:12px 0;">Aucune étape pour l'instant.</div>`;
    return;
  }
  list.innerHTML = state.steps
    .map(
      (step, i) => `
      <div class="step-row js-step-row" data-index="${i}" style="cursor:pointer;${state.editingIndex === i ? "border-color:var(--accent);background:var(--accent-tint);" : ""}">
        ${stepIconHtml(step.kind)}
        <div style="flex:1;min-width:0;">
          <div style="font-size:13px;font-weight:600;">${i + 1}. ${escapeHtml(STEP_KINDS[step.kind].label)} &mdash; ${escapeHtml(step.name)}</div>
          <div style="font-size:12px;color:var(--text-faint);">${escapeHtml(stepSummary(step))}</div>
        </div>
        <div style="display:flex;flex-direction:column;">
          <button class="step-remove js-step-up" data-index="${i}" title="Monter" type="button" ${i === 0 ? "disabled style='opacity:.3;'" : ""}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M5 15l7-7 7 7"/></svg>
          </button>
          <button class="step-remove js-step-down" data-index="${i}" title="Descendre" type="button" ${i === state.steps.length - 1 ? "disabled style='opacity:.3;'" : ""}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M5 9l7 7 7-7"/></svg>
          </button>
        </div>
        <button class="step-remove js-step-remove" data-index="${i}" title="Retirer" type="button">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 5l14 14M5 19L19 5"/></svg>
        </button>
      </div>`
    )
    .join("");
  list.querySelectorAll(".js-step-row").forEach((row) => {
    row.addEventListener("click", (event) => {
      if (event.target.closest("button")) return;
      startEditingStep(parseInt(row.dataset.index, 10));
    });
  });
  list.querySelectorAll(".js-step-remove").forEach((btn) => {
    btn.addEventListener("click", () => {
      const index = parseInt(btn.dataset.index, 10);
      state.steps.splice(index, 1);
      if (state.editingIndex === index) cancelEditingStep();
      renderSteps();
    });
  });
  list.querySelectorAll(".js-step-up").forEach((btn) => {
    btn.addEventListener("click", () => moveStep(parseInt(btn.dataset.index, 10), -1));
  });
  list.querySelectorAll(".js-step-down").forEach((btn) => {
    btn.addEventListener("click", () => moveStep(parseInt(btn.dataset.index, 10), 1));
  });
  refreshCampaignFactorSteps();
  state.campaignPlan = null;
  document.getElementById("campaign-result").innerHTML = "";
}

function fillKindFields(step) {
  document.getElementById("kind-select").value = step.kind;
  renderKindFields(step.kind);
  document.getElementById("f-name").value = step.name;
  if (step.kind === "deposition") {
    document.getElementById("f-material").value = step.material;
    document.getElementById("f-recipe").value = step.recipe;
    document.getElementById("f-thickness").value = step.thickness.value;
    document.getElementById("f-thickness-unit").value = step.thickness.unit;
  } else if (step.kind === "etch") {
    document.getElementById("f-recipe").value = step.recipe;
    document.getElementById("f-depth").value = step.depth.value;
    document.getElementById("f-depth-unit").value = step.depth.unit;
  } else if (step.kind === "planarization") {
    const mode = step.target_level ? "level" : "material";
    document.getElementById("f-plana-mode").value = mode;
    document.getElementById("f-plana-mode").dispatchEvent(new Event("change"));
    if (mode === "level") {
      document.getElementById("f-target-level").value = step.target_level.value;
      document.getElementById("f-target-level-unit").value = step.target_level.unit;
    } else {
      document.getElementById("f-stop-material").value = step.stop_material;
    }
  } else if (step.kind === "lithography") {
    document.getElementById("f-resist-material").value = step.resist_material;
    document.getElementById("f-thickness").value = step.thickness.value;
    document.getElementById("f-thickness-unit").value = step.thickness.unit;
    document.getElementById("f-openings").value = step.openings.map((pair) => pair.join("-")).join(", ");
  } else if (step.kind === "chemical") {
    document.getElementById("f-description").value = step.description || "";
  } else if (step.kind === "resist_strip") {
    document.getElementById("f-material").value = step.material;
  }
}

function startEditingStep(index) {
  state.editingIndex = index;
  fillKindFields(state.steps[index]);
  document.getElementById("step-form-title").textContent = `Modifier l'étape ${index + 1}`;
  document.getElementById("add-step-btn-label").textContent = "Enregistrer les modifications";
  document.getElementById("cancel-edit-btn").style.display = "";
  renderSteps();
}

function cancelEditingStep() {
  state.editingIndex = null;
  document.getElementById("step-form-title").textContent = "Ajouter une étape";
  document.getElementById("add-step-btn-label").textContent = "Ajouter cette étape";
  document.getElementById("cancel-edit-btn").style.display = "none";
  renderKindFields(document.getElementById("kind-select").value);
  renderSteps();
}

function moveStep(index, delta) {
  const target = index + delta;
  if (target < 0 || target >= state.steps.length) return;
  const [step] = state.steps.splice(index, 1);
  state.steps.splice(target, 0, step);
  if (state.editingIndex === index) state.editingIndex = target;
  else if (state.editingIndex === target) state.editingIndex = index;
  renderSteps();
}

function renderObjectives() {
  const list = document.getElementById("objectives-list");
  list.innerHTML = state.objectives
    .map(
      (o, i) => `
      <div class="step-row" style="align-items:flex-start;">
        <div style="flex:1;min-width:0;">
          <div style="font-size:13px;font-weight:600;">${escapeHtml(o.name)}</div>
          <div style="font-size:12px;color:var(--text-faint);">${escapeHtml(o.metric)} &middot; ${escapeHtml(o.direction)}${o.target != null ? " · cible " + o.target : ""}</div>
          ${o.rationale ? `<div style="font-size:12px;color:var(--text-soft);margin-top:4px;">${escapeHtml(o.rationale)}</div>` : ""}
          ${o.verification_method ? `<div style="font-size:11.5px;color:var(--text-faint);margin-top:2px;">Vérification : ${escapeHtml(o.verification_method)}</div>` : ""}
        </div>
        <button class="step-remove" data-index="${i}" type="button">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 5l14 14M5 19L19 5"/></svg>
        </button>
      </div>`
    )
    .join("");
  list.querySelectorAll(".step-remove").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.objectives.splice(parseInt(btn.dataset.index, 10), 1);
      renderObjectives();
    });
  });
}

const CAMPAIGN_FIELD_OPTIONS = {
  deposition: [["thickness", "Épaisseur"]],
  etch: [["depth", "Profondeur"]],
  planarization: [["target_level", "Niveau cible"]],
  lithography: [["thickness", "Épaisseur"]],
  chemical: [],
  resist_strip: [],
};

function campaignStepOptionsHtml() {
  if (state.steps.length === 0) return `<option value="">Ajoutez au moins une étape d'abord</option>`;
  return state.steps
    .map((s, i) => `<option value="${i}">${i + 1}. ${escapeHtml(STEP_KINDS[s.kind].label)} — ${escapeHtml(s.name)}</option>`)
    .join("");
}

function campaignFieldOptionsHtml(stepIndex) {
  const step = state.steps[stepIndex];
  const options = step ? CAMPAIGN_FIELD_OPTIONS[step.kind] || [] : [];
  return options.length
    ? options.map(([value, label]) => `<option value="${value}">${label}</option>`).join("")
    : `<option value="">Aucun paramètre modifiable sur cette étape</option>`;
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
    const field = row.querySelector(".js-factor-field").value;
    const values = row
      .querySelector(".js-factor-values")
      .value.split(",")
      .map((v) => parseFloat(v.trim()))
      .filter((v) => !Number.isNaN(v));
    if (Number.isNaN(stepIndex) || !field || values.length === 0) return null;
    factors.push({ step_index: stepIndex, field, values });
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

function renderScrubber() {
  const track = document.getElementById("scrubber-track");
  const label = document.getElementById("scrubber-label");
  if (!state.frames || state.frames.length === 0) {
    track.innerHTML = "";
    label.textContent = "Pas encore simulé";
    return;
  }
  const n = state.frames.length;
  track.innerHTML = state.frames
    .map((f, i) => {
      const pct = n === 1 ? 0 : (i / (n - 1)) * 100;
      return `<div class="scrubber-dot" data-index="${i}" style="left:${pct}%;"></div>`;
    })
    .join("");
  track.querySelectorAll(".scrubber-dot").forEach((dot) => {
    dot.addEventListener("click", () => {
      state.currentFrame = parseInt(dot.dataset.index, 10);
      renderFrame();
    });
  });
  const current = state.frames[state.currentFrame];
  label.textContent = `${state.currentFrame + 1} / ${n} · ${current.step_name}`;
}

function renderFrame() {
  const frame = state.frames ? state.frames[state.currentFrame] : null;
  document.getElementById("svg-container").innerHTML = frame ? frame.svg : "";
  const legend = document.getElementById("legend");
  const materials = frame ? frame.materials : [];
  legend.innerHTML = materials
    .map((name) => `<div class="legend-item"><span class="legend-swatch" style="background:${state.materialColors[name] || "#999"};"></span>${escapeHtml(name)}</div>`)
    .join("");
  renderScrubber();
}

async function loadPickers() {
  state.materials = await api.get(`/api/projects/${slug}/materials`);
  state.recipes = await api.get(`/api/projects/${slug}/recipes`);
  document.getElementById("substrate-material").innerHTML = materialOptions("Si");
  renderKindFields(document.getElementById("kind-select").value);
}

async function loadExistingProcess() {
  if (!evolveExperienceId) return;
  try {
    const data = await api.get(`/api/projects/${slug}/experiences/${evolveExperienceId}/process`);
    document.getElementById("substrate-material").value = data.substrate.material;
    document.getElementById("substrate-width").value = data.substrate.domain_width.value;
    document.getElementById("substrate-width-unit").value = data.substrate.domain_width.unit;
    document.getElementById("substrate-thickness").value = data.substrate.thickness.value;
    document.getElementById("substrate-thickness-unit").value = data.substrate.thickness.unit;
    state.steps = data.steps;
    renderSteps();
    document.getElementById("page-title").textContent = "Enregistrer une évolution";
    document.getElementById("launch-btn").textContent = "Enregistrer cette évolution";

    const detail = await api.get(`/api/projects/${slug}/experiences/${evolveExperienceId}`);
    document.getElementById("exp-title").value = detail.title;
    document.getElementById("exp-intent").value = detail.intent;
    document.getElementById("exp-hypothesis").value = detail.hypothesis || "";
    const verification = detail.objective_verification || {};
    state.objectives = detail.objectives.map((o) => ({ ...o, verification_method: verification[o.name] || null }));
    renderObjectives();
  } catch (err) {
    showError(err);
  }
}

function substrateSpec() {
  return {
    material: document.getElementById("substrate-material").value,
    domain_width: lengthValue("substrate-width"),
    thickness: lengthValue("substrate-thickness"),
  };
}

document.getElementById("kind-select").addEventListener("change", (e) => renderKindFields(e.target.value));

document.getElementById("add-step-btn").addEventListener("click", () => {
  clearError();
  try {
    const step = buildStepFromForm();
    if (state.editingIndex !== null) {
      state.steps[state.editingIndex] = step;
      cancelEditingStep();
    } else {
      state.steps.push(step);
      renderSteps();
    }
  } catch (err) {
    showError(err);
  }
});

document.getElementById("cancel-edit-btn").addEventListener("click", () => {
  clearError();
  cancelEditingStep();
});

document.getElementById("objective-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const name = document.getElementById("obj-name").value.trim();
  const metric = document.getElementById("obj-metric").value.trim();
  if (!name || !metric) return;
  const targetRaw = document.getElementById("obj-target").value;
  state.objectives.push({
    name,
    metric,
    direction: document.getElementById("obj-direction").value,
    target: targetRaw ? parseFloat(targetRaw) : null,
    rationale: document.getElementById("obj-rationale").value.trim() || null,
    verification_method: document.getElementById("obj-verification").value.trim() || null,
  });
  document.getElementById("objective-form").reset();
  renderObjectives();
});

document.getElementById("simulate-btn").addEventListener("click", async () => {
  clearError();
  try {
    const result = await api.post(`/api/projects/${slug}/structures/simulate`, {
      substrate: substrateSpec(),
      steps: state.steps,
    });
    state.frames = result.frames;
    state.materialColors = result.material_colors;
    state.currentFrame = state.frames.length - 1;
    renderFrame();
  } catch (err) {
    showError(err);
  }
});

document.getElementById("launch-btn").addEventListener("click", async () => {
  clearError();
  const title = document.getElementById("exp-title").value.trim();
  const intent = document.getElementById("exp-intent").value.trim();
  if (!title || !intent) {
    showError(new Error("Le titre et l'intention sont obligatoires."));
    return;
  }
  const payload = {
    substrate: substrateSpec(),
    steps: state.steps,
    title,
    intent,
    hypothesis: document.getElementById("exp-hypothesis").value || null,
    objectives: state.objectives,
  };
  if (evolveExperienceId && document.getElementById("branch-fork").checked) {
    const branchName = document.getElementById("new-branch-name").value.trim();
    if (!branchName) {
      showError(new Error("Donnez un nom à la nouvelle piste."));
      return;
    }
    payload.new_branch = branchName;
  }
  try {
    let endpoint;
    if (state.campaignPlan) {
      payload.plan = state.campaignPlan;
      endpoint = `/api/projects/${slug}/experiences/campagne`;
    } else if (evolveExperienceId) {
      endpoint = `/api/projects/${slug}/experiences/${evolveExperienceId}/evoluer`;
    } else {
      endpoint = `/api/projects/${slug}/experiences`;
    }
    const result = await api.post(endpoint, payload);
    window.location.href = `/projets/${slug}/experiences/${result.id}`;
  } catch (err) {
    showError(err);
  }
});

document.getElementById("branch-continue").addEventListener("change", () => {
  document.getElementById("new-branch-name").style.display = "none";
});
document.getElementById("branch-fork").addEventListener("change", () => {
  document.getElementById("new-branch-name").style.display = "";
});

async function loadTemplateProcess() {
  if (!templateExperienceId) return;
  document.getElementById("page-title").textContent = "Nouvelle expérience (structure reprise)";
  try {
    const data = await api.get(`/api/projects/${slug}/experiences/${templateExperienceId}/process`);
    document.getElementById("substrate-material").value = data.substrate.material;
    document.getElementById("substrate-width").value = data.substrate.domain_width.value;
    document.getElementById("substrate-width-unit").value = data.substrate.domain_width.unit;
    document.getElementById("substrate-thickness").value = data.substrate.thickness.value;
    document.getElementById("substrate-thickness-unit").value = data.substrate.thickness.unit;
    state.steps = data.steps;
    renderSteps();
  } catch (err) {
    showError(err);
  }
}

async function init() {
  document.getElementById("crumb").textContent = "/ " + slug;
  if (evolveExperienceId) {
    document.getElementById("campaign-section").style.display = "none";
    document.getElementById("branch-choice-wrap").style.display = "block";
  }
  await loadPickers();
  renderSteps();
  renderObjectives();
  renderFrame();
  await loadExistingProcess();
  await loadTemplateProcess();
  addCampaignFactorRow();
}

init();
