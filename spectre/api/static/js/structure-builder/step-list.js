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

function stepSelectCheckboxHtml(i) {
  return `<input type="checkbox" class="js-step-select" data-index="${i}" ${state.selectedStepIndices.has(i) ? "checked" : ""} title="Sélectionner pour grouper en brique" style="margin-top:2px;flex:none;cursor:pointer;">`;
}

function stepRowHtml(step, i, compact) {
  const highlight = state.editingIndex === i ? "border-color:var(--accent);background:var(--accent-tint);" : "";
  if (compact) {
    return `
      <div class="step-row js-step-row" data-index="${i}" style="cursor:pointer;${highlight}">
        ${stepSelectCheckboxHtml(i)}
        ${stepIconHtml(step.kind)}
        <div style="flex:1;min-width:0;font-size:13px;font-weight:600;">${i + 1}. ${escapeHtml(step.name)}</div>
        <button class="step-remove js-step-remove" data-index="${i}" title="Retirer" type="button">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 5l14 14M5 19L19 5"/></svg>
        </button>
      </div>`;
  }
  return `
    <div class="step-row js-step-row" data-index="${i}" style="cursor:pointer;${highlight}">
      ${stepSelectCheckboxHtml(i)}
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

// Regroupe les étapes consécutives partageant le même brick_group_id (voir BrickTag côté
// StructureForge) sous un bloc visuel commun - une étape sans groupe reste une ligne nue. Le
// groupement est déterminé uniquement par cette étiquette persistée sur l'étape elle-même, pas
// par un état séparé côté client : il survit donc à un rechargement de la structure.
function stepsListHtml(compact) {
  const parts = [];
  let i = 0;
  while (i < state.steps.length) {
    const groupId = state.steps[i].brick_group_id;
    if (!groupId) {
      parts.push(stepRowHtml(state.steps[i], i, compact));
      i += 1;
      continue;
    }
    const rows = [];
    const brickName = state.steps[i].brick_name;
    let j = i;
    while (j < state.steps.length && state.steps[j].brick_group_id === groupId) {
      rows.push(stepRowHtml(state.steps[j], j, compact));
      j += 1;
    }
    parts.push(`
      <div class="step-brick-group" style="border:1.5px dashed var(--accent);border-radius:var(--radius-sm);padding:8px;display:flex;flex-direction:column;gap:8px;">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
          <div style="font-size:11px;font-weight:700;color:var(--accent);text-transform:uppercase;letter-spacing:.02em;">🧱 ${escapeHtml(brickName || "Brique")}</div>
          <button class="js-ungroup-brick" data-group-id="${escapeHtml(groupId)}" type="button" style="background:none;border:none;cursor:pointer;color:var(--text-faint);font-size:11px;">Dissocier</button>
        </div>
        ${rows.join("")}
      </div>`);
    i = j;
  }
  return parts.join("");
}

function generateBrickGroupId() {
  return `brick-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

// Une brique enregistrée dans la bibliothèque reste "propre" (jamais étiquetée) - l'étiquette
// n'existe que sur les copies vivantes dans une structure en cours, posée fraîche à chaque
// groupement ou insertion (voir plus bas).
function stripBrickTag(step) {
  const { brick_group_id, brick_name, ...rest } = step;
  return rest;
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
    list.innerHTML = stepsListHtml(compact);
    list.querySelectorAll(".js-step-row").forEach((row) => {
      row.addEventListener("click", (event) => {
        if (event.target.closest("button") || event.target.closest("input")) return;
        startEditingStep(parseInt(row.dataset.index, 10));
      });
    });
    list.querySelectorAll(".js-step-remove").forEach((btn) => {
      btn.addEventListener("click", () => {
        const index = parseInt(btn.dataset.index, 10);
        state.steps.splice(index, 1);
        state.selectedStepIndices.clear();
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
    list.querySelectorAll(".js-step-select").forEach((cb) => {
      cb.addEventListener("click", (event) => event.stopPropagation());
      cb.addEventListener("change", () => {
        toggleStepSelection(parseInt(cb.dataset.index, 10), cb.checked);
      });
    });
    list.querySelectorAll(".js-ungroup-brick").forEach((btn) => {
      btn.addEventListener("click", () => {
        const groupId = btn.dataset.groupId;
        state.steps.forEach((s, i) => {
          if (s.brick_group_id === groupId) state.steps[i] = { ...s, brick_group_id: null, brick_name: null };
        });
        renderSteps();
      });
    });
  }
  refreshCampaignFactorSteps();
  state.campaignPlan = null;
  document.getElementById("campaign-result").innerHTML = "";
  updateStepFormVisibility();
  updateGroupBrickWrapVisibility();
  highlightSelectedLayer();
  scheduleSimulate();
}

// Sélection par cases à cocher pour "grouper en brique" (voir #group-brick-btn plus bas) - toute
// modification structurelle de la liste (ajout, retrait, déplacement, insertion) invalide les
// indices choisis, donc `state.selectedStepIndices` est vidé à chaque fois ailleurs dans ce fichier.
function toggleStepSelection(index, checked) {
  if (checked) state.selectedStepIndices.add(index);
  else state.selectedStepIndices.delete(index);
  updateGroupBrickWrapVisibility();
}

function updateGroupBrickWrapVisibility() {
  const wrap = document.getElementById("group-brick-wrap");
  const count = state.selectedStepIndices.size;
  wrap.style.display = count > 0 ? "" : "none";
  document.getElementById("group-brick-count").textContent =
    count === 1 ? "1 étape sélectionnée" : `${count} étapes sélectionnées`;
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
  state.selectedStepIndices.clear();
  renderSteps();
}

document.getElementById("kind-select").addEventListener("change", (e) => renderKindFields(e.target.value));

document.getElementById("add-step-btn").addEventListener("click", () => {
  clearError();
  try {
    const step = buildStepFromForm();
    if (state.editingIndex !== null) {
      // Éditer un champ d'une étape déjà groupée ne doit pas la dissocier silencieusement de sa
      // brique - on reporte l'étiquette de l'ancienne étape sur la nouvelle.
      const previous = state.steps[state.editingIndex];
      state.steps[state.editingIndex] = { ...step, brick_group_id: previous.brick_group_id, brick_name: previous.brick_name };
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

// Une brique technologique est une séquence d'étapes préenregistrée (voir brick-mode.js /
// spectre.core.tech_bricks) - l'insérer copie ses étapes dans la structure courante une bonne
// fois pour toutes, comme un préset : aucun lien vivant après coup avec la brique elle-même.
function populateInsertBrickSelect() {
  const select = document.getElementById("insert-brick-select");
  const entries = [
    ...state.techBricks.presets.map((b) => ({ ...b, scope: "preset" })),
    ...state.techBricks.partagees.map((b) => ({ ...b, scope: "partagee" })),
    ...state.techBricks.projet.map((b) => ({ ...b, scope: "projet" })),
  ];
  const scopeSuffix = { preset: " (préset)", partagee: " (partagée)", projet: "" };
  select.innerHTML =
    `<option value="">— choisir —</option>` +
    entries
      .map((b) => `<option value="${b.scope}::${encodeURIComponent(b.name)}">${escapeHtml(b.name)}${scopeSuffix[b.scope]}</option>`)
      .join("");
}

document.getElementById("insert-brick-btn").addEventListener("click", () => {
  clearError();
  const [scope, encodedName] = document.getElementById("insert-brick-select").value.split("::");
  if (!scope) return;
  const name = decodeURIComponent(encodedName);
  const bucket = scope === "preset" ? state.techBricks.presets : scope === "partagee" ? state.techBricks.partagees : state.techBricks.projet;
  const brick = bucket.find((b) => b.name === name);
  if (!brick) return;
  const insertAt = state.editingIndex !== null ? state.editingIndex : state.steps.length;
  const groupId = generateBrickGroupId();
  const copiedSteps = JSON.parse(JSON.stringify(brick.steps)).map((s) => ({ ...s, brick_group_id: groupId, brick_name: brick.name }));
  state.steps.splice(insertAt, 0, ...copiedSteps);
  if (state.editingIndex !== null) state.editingIndex += copiedSteps.length;
  state.selectedStepIndices.clear();
  document.getElementById("insert-brick-select").value = "";
  renderSteps();
});

// Grouper une sélection d'étapes déjà présentes dans la structure en cours en une nouvelle brique
// réutilisable - l'inverse de "insérer une brique" ci-dessus. L'ordre des étapes étant physiquement
// significatif (la simulation dépend de la séquence), seule une sélection contiguë peut être
// bracketée sensément ; une sélection éparpillée est refusée plutôt que silencieusement réordonnée.
document.getElementById("group-brick-btn").addEventListener("click", async () => {
  clearError();
  const indices = Array.from(state.selectedStepIndices).sort((a, b) => a - b);
  if (indices.length === 0) return;
  const contiguous = indices.every((idx, k) => k === 0 || idx === indices[k - 1] + 1);
  if (!contiguous) {
    showError(new Error("Les étapes sélectionnées doivent être consécutives pour former une brique."));
    return;
  }
  const name = document.getElementById("group-brick-name").value.trim();
  if (!name) {
    showError(new Error("Donnez un nom à la brique."));
    return;
  }
  try {
    const selectedSteps = indices.map((idx) => stripBrickTag(state.steps[idx]));
    state.techBricks = await api.post(`/api/projects/${slug}/briques-technologiques`, { name, steps: selectedSteps, partagee: false });
    const groupId = generateBrickGroupId();
    indices.forEach((idx) => {
      state.steps[idx] = { ...state.steps[idx], brick_group_id: groupId, brick_name: name };
    });
    populateInsertBrickSelect();
    state.selectedStepIndices.clear();
    document.getElementById("group-brick-name").value = "";
    renderSteps();
  } catch (err) {
    showError(err);
  }
});
