/* Liste des étapes : rendu (mode "par couches" compact vs "par étapes" détaillé), ajout/édition/
   suppression/réordonnancement, et le formulaire d'ajout/édition lui-même (délègue tout ce qui est
   spécifique à un type d'étape à step-kinds.js). */

function fillKindFields(step) {
  document.getElementById("kind-select").value = step.kind;
  renderKindFields(step.kind);
  document.getElementById("f-name").value = step.name;
  const def = STEP_KIND_DEFS[step.kind];
  if (def.fillFields) def.fillFields(step);
}

function stepRowHtml(step, i, compact) {
  const highlight = state.editingIndex === i ? "border-color:var(--accent);background:var(--accent-tint);" : "";
  if (compact) {
    return `
      <div class="step-row js-step-row" data-index="${i}" style="cursor:pointer;${highlight}">
        ${stepIconHtml(step.kind)}
        <div style="flex:1;min-width:0;font-size:13px;font-weight:600;">${i + 1}. ${escapeHtml(step.name)}</div>
        <button class="step-remove js-step-remove" data-index="${i}" title="Retirer" type="button">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 5l14 14M5 19L19 5"/></svg>
        </button>
      </div>`;
  }
  return `
    <div class="step-row js-step-row" data-index="${i}" style="cursor:pointer;${highlight}">
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
    </div>`;
}

function updateViewModeAvailability() {
  const eligible = state.steps.length === 0 || state.steps.every((s) => s.kind === "deposition");
  const couchesBtn = document.getElementById("view-mode-couches");
  couchesBtn.disabled = !eligible;
  couchesBtn.title = eligible
    ? ""
    : "Disponible uniquement pour un empilement de dépôts (pas de gravure, planarisation, lithographie...)";
  if (!eligible && state.viewMode === "couches") {
    state.viewMode = "etapes";
    state.showStepForm = true;
    document.getElementById("view-mode-help").textContent =
      "Passé en vue par étapes : cette structure contient une étape autre que dépôt.";
  }
  couchesBtn.classList.toggle("active", state.viewMode === "couches");
  document.getElementById("view-mode-etapes").classList.toggle("active", state.viewMode === "etapes");
  document.getElementById("steps-list-help").textContent =
    state.viewMode === "couches"
      ? "Cliquez une couche (dans le dessin ou ci-dessous) pour l'éditer."
      : "Cliquez une étape pour la modifier ; ▲▼ pour la déplacer.";
}

function updateStepFormVisibility() {
  const formVisible = state.viewMode === "etapes" || state.editingIndex !== null || state.showStepForm;
  document.getElementById("step-form-section").style.display = formVisible ? "" : "none";
  document.getElementById("context-panel-empty").style.display = formVisible ? "none" : "";
  document.getElementById("add-step-shortcut-btn").style.display =
    !formVisible && state.viewMode === "couches" ? "" : "none";
  document.getElementById("cancel-edit-btn").style.display =
    state.editingIndex !== null || (state.viewMode === "couches" && state.showStepForm) ? "" : "none";
}

function highlightSelectedLayer() {
  const container = document.getElementById("svg-container");
  container.querySelectorAll("[data-layer-index]").forEach((path) => {
    const stepIndex = parseInt(path.dataset.layerIndex, 10) - 1; // layer 0 is always the substrate
    const selected = state.viewMode === "couches" && state.editingIndex === stepIndex;
    path.style.stroke = selected ? "var(--accent)" : "";
    path.style.strokeWidth = selected ? "2.5" : "";
  });
}

function renderSteps() {
  updateViewModeAvailability(); // may fall back to étapes mode before we render rows below
  const list = document.getElementById("steps-list");
  document.getElementById("steps-count").textContent = state.steps.length;
  if (state.steps.length === 0) {
    list.innerHTML = `<div class="help" style="padding:12px 0;">Aucune étape pour l'instant.</div>`;
  } else {
    const compact = state.viewMode === "couches";
    list.innerHTML = state.steps.map((step, i) => stepRowHtml(step, i, compact)).join("");
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
        else renderSteps();
      });
    });
    list.querySelectorAll(".js-step-up").forEach((btn) => {
      btn.addEventListener("click", () => moveStep(parseInt(btn.dataset.index, 10), -1));
    });
    list.querySelectorAll(".js-step-down").forEach((btn) => {
      btn.addEventListener("click", () => moveStep(parseInt(btn.dataset.index, 10), 1));
    });
  }
  refreshCampaignFactorSteps();
  state.campaignPlan = null;
  document.getElementById("campaign-result").innerHTML = "";
  updateStepFormVisibility();
  highlightSelectedLayer();
  scheduleSimulate();
}

function startEditingStep(index) {
  state.editingIndex = index;
  fillKindFields(state.steps[index]);
  document.getElementById("step-form-title").textContent = `Modifier l'étape ${index + 1}`;
  document.getElementById("add-step-btn-label").textContent = "Enregistrer les modifications";
  renderSteps();
}

function cancelEditingStep() {
  state.editingIndex = null;
  if (state.viewMode === "couches") state.showStepForm = false;
  document.getElementById("step-form-title").textContent = "Ajouter une étape";
  document.getElementById("add-step-btn-label").textContent = "Ajouter cette étape";
  renderKindFields(document.getElementById("kind-select").value);
  renderSteps();
}

function startAddingStep() {
  state.editingIndex = null;
  state.showStepForm = true;
  document.getElementById("step-form-title").textContent = "Ajouter une étape";
  document.getElementById("add-step-btn-label").textContent = "Ajouter cette étape";
  renderKindFields(document.getElementById("kind-select").value);
  renderSteps();
}

function setViewMode(mode) {
  state.viewMode = mode;
  state.showStepForm = false;
  document.getElementById("view-mode-help").textContent =
    mode === "couches"
      ? "Cliquez une couche du dessin pour l'éditer. Disponible tant que la structure n'est faite que de dépôts (empilement d'épitaxie)."
      : "Cliquez une étape pour la modifier ; ▲▼ pour la déplacer.";
  renderSteps();
}

document.getElementById("view-mode-couches").addEventListener("click", () => setViewMode("couches"));
document.getElementById("view-mode-etapes").addEventListener("click", () => setViewMode("etapes"));

document.getElementById("add-step-shortcut-btn").addEventListener("click", startAddingStep);

document.getElementById("svg-container").addEventListener("click", (event) => {
  if (state.viewMode !== "couches") return;
  const path = event.target.closest("[data-layer-index]");
  if (!path) return;
  const layerIndex = parseInt(path.dataset.layerIndex, 10);
  if (layerIndex === 0) {
    document.getElementById("substrate-section").scrollIntoView({ behavior: "smooth", block: "center" });
    return;
  }
  const stepIndex = layerIndex - 1;
  if (stepIndex >= 0 && stepIndex < state.steps.length) startEditingStep(stepIndex);
});

function moveStep(index, delta) {
  const target = index + delta;
  if (target < 0 || target >= state.steps.length) return;
  const [step] = state.steps.splice(index, 1);
  state.steps.splice(target, 0, step);
  if (state.editingIndex === index) state.editingIndex = target;
  else if (state.editingIndex === target) state.editingIndex = index;
  renderSteps();
}

document.getElementById("kind-select").addEventListener("change", (e) => renderKindFields(e.target.value));

document.getElementById("add-step-btn").addEventListener("click", () => {
  clearError();
  try {
    const step = buildStepFromForm();
    if (state.editingIndex !== null) {
      state.steps[state.editingIndex] = step;
    } else {
      state.steps.push(step);
    }
    cancelEditingStep();
  } catch (err) {
    showError(err);
  }
});

document.getElementById("cancel-edit-btn").addEventListener("click", () => {
  clearError();
  cancelEditingStep();
});
