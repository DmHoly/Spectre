/* Inspecteur : le panneau de droite de l'atelier, contextuel à la sélection du process flow -
   substrat, étape (formulaire de son type, délégué à step-kinds.js), sélection multiple (grouper
   en brique, supprimer), brique (replier, dissocier, supprimer) ; à l'écran variations, c'est
   variations.js qui y place son propre formulaire.

   Une étape s'édite en direct : chaque frappe met à jour state.steps[selectedIndex], la puce du
   flow et le dessin (aperçu), et chaque valeur retenue (évènement "change") entre dans
   l'historique - Ctrl+Z remplace l'ancien bouton « Annuler la modification ». */

const INSPECTOR_SECTIONS = [
  "context-panel-empty",
  "substrate-section",
  "step-form-section",
  "group-brick-wrap",
  "brick-group-section",
  "variation-form-section",
];

function showInspectorSection(id) {
  INSPECTOR_SECTIONS.forEach((sectionId) => {
    document.getElementById(sectionId).hidden = sectionId !== id;
  });
}

function showInspectorEmpty(text) {
  document.getElementById("context-panel-empty-text").textContent = text;
  showInspectorSection("context-panel-empty");
}

function renderInspector() {
  if (state.wizardScreen === "variations") {
    renderVariationInspector();
    return;
  }
  if (hasMultiSelection()) {
    renderMultiInspector();
  } else if (state.selectedBrickGroup && brickGroupSpan(state.selectedBrickGroup)) {
    renderBrickGroupInspector();
  } else if (state.selectedIndex >= 0 && state.selectedIndex < state.steps.length) {
    renderStepInspector();
  } else {
    state.selectedBrickGroup = null;
    showInspectorSection("substrate-section");
  }
}

// Premier champ utile de l'inspecteur (Entrée / double-clic sur une puce).
function focusInspector() {
  const panel = document.getElementById("context-panel");
  const target = panel.querySelector(".sb-insp:not([hidden]) .sb-insp__body input:not([type=checkbox]), .sb-insp:not([hidden]) .sb-insp__body select");
  if (target) target.focus();
}

// ---------------------------------------------------------------------------------------------
// Étape
// ---------------------------------------------------------------------------------------------

function populateKindSelect() {
  document.getElementById("kind-select").innerHTML = TOOL_ORDER.map(
    (kind) => `<option value="${kind}">${escapeHtml(STEP_KIND_DEFS[kind].label)}${TOOL_HINTS[kind] ? ` (${escapeHtml(TOOL_HINTS[kind])})` : ""}</option>`
  ).join("");
}

function fillKindFields(step) {
  document.getElementById("kind-select").value = step.kind;
  state.formDeclaredParams = JSON.parse(JSON.stringify(step.declaredParams || []));
  state.formLayerLabel = step.layerLabel ? JSON.parse(JSON.stringify(step.layerLabel)) : null;
  setFormOwnRecipe(step);
  renderKindFields(step.kind);
  document.getElementById("f-name").value = step.name;
  const def = STEP_KIND_DEFS[step.kind];
  if (def.fillFields) def.fillFields(step);
  refreshLayerLabelValues(step);
}

// Les valeurs par défaut d'un type d'étape sont celles de son formulaire (step-kinds.js) - on le
// rend dans l'inspecteur puis on le lit, plutôt que de dupliquer ces défauts ailleurs.
function defaultStepOfKind(kind) {
  state.formDeclaredParams = [];
  state.formLayerLabel = null;
  setFormOwnRecipe(null);
  document.getElementById("kind-select").value = kind;
  renderKindFields(kind);
  return buildStepFromForm();
}

function renderStepInspector() {
  showInspectorSection("step-form-section");
  fillKindFields(state.steps[state.selectedIndex]);
  updateStepInspectorHeader();
  renderPresetPanel();
}

function updateStepInspectorHeader() {
  const i = state.selectedIndex;
  const step = state.steps[i];
  if (!step) return;
  const def = STEP_KIND_DEFS[step.kind];
  document.getElementById("step-form-icon").innerHTML = stepIconHtml(step.kind);
  const brick = step.brick_name ? ` · brique ${step.brick_name}` : "";
  document.getElementById("step-form-eyebrow").textContent = `Étape ${i + 1} / ${state.steps.length} · ${def.label}${brick}`;
  document.getElementById("step-form-title").textContent = step.name;
  const [start, end] = brickSpanAt(i);
  const inBrick = Boolean(step.brick_group_id);
  const left = document.getElementById("step-move-left-btn");
  const right = document.getElementById("step-move-right-btn");
  left.disabled = start === 0;
  right.disabled = end === state.steps.length - 1;
  const moveHint = inBrick ? " - déplace toute la brique" : "";
  left.title = `Déplacer avant (Ctrl+←)${moveHint}`;
  right.title = `Déplacer après (Ctrl+→)${moveHint}`;
}

// Aperçu/édition en direct : appelé à chaque frappe ou sélection dans le formulaire (délégué sur
// son conteneur stable, #kind-fields étant reconstruit à chaque changement de type) - et aussi par
// step-kinds.js / form-widgets.js quand un script pose une valeur sans évènement (réseau de litho,
// retrait d'un paramètre déclaré).
function livePreviewFromForm() {
  if (state.wizardScreen === "variations") return;
  const i = state.selectedIndex;
  if (i == null || i < 0 || i >= state.steps.length || hasMultiSelection()) return;
  let step;
  try {
    step = buildStepFromForm();
  } catch (err) {
    return; // valeur transitoire pas encore exploitable - on attend la suite de la frappe
  }
  // Éditer une étape groupée ne doit pas la dissocier silencieusement de sa brique ; ni lui
  // faire perdre son identité (son id, voir withoutStepId dans step-list.js).
  const previous = state.steps[i];
  if (previous.id) step.id = previous.id;
  if (previous.presetOrigin) step.presetOrigin = previous.presetOrigin; // sa trace, pas un lien : l'étape garde ses modifications
  if (previous.brick_group_id) {
    step.brick_group_id = previous.brick_group_id;
    step.brick_name = previous.brick_name;
    if (previous.brick_source) step.brick_source = previous.brick_source;
  }
  state.steps[i] = step;
  shareOwnRecipe(step, previous.ownRecipe ? previous.ownRecipe.name : null);
  refreshLayerLabelValues(step);
  refreshPresetStatus();
  updateStepInspectorHeader();
  invalidateVariations();
  renderRail();
  scheduleSimulate();
}

const stepFormSection = document.getElementById("step-form-section");
document.getElementById("kind-select").addEventListener("change", (e) => {
  setFormOwnRecipe(null);
  renderKindFields(e.target.value);
});
stepFormSection.addEventListener("input", (e) => {
  // changement de type : attendre son "change", qui reconstruit d'abord les champs du nouveau type
  if (e.target.id !== "kind-select") livePreviewFromForm();
});
stepFormSection.addEventListener("change", () => {
  livePreviewFromForm();
  captureHistory();
});
// Boutons du formulaire qui modifient l'étape par script (« Générer les ouvertures », ajout/retrait
// d'un paramètre déclaré) : leur effet entre dans l'historique une fois leur propre gestionnaire passé.
stepFormSection.addEventListener("click", (e) => {
  if (e.target.closest("#kind-fields button")) setTimeout(captureHistory, 0);
});

document.getElementById("step-move-left-btn").addEventListener("click", () => moveStep(state.selectedIndex, -1));
document.getElementById("step-move-right-btn").addEventListener("click", () => moveStep(state.selectedIndex, 1));
document.getElementById("step-duplicate-btn").addEventListener("click", () => duplicateStep(state.selectedIndex));
document.getElementById("step-delete-btn").addEventListener("click", () => deleteSteps([state.selectedIndex]));

// ---------------------------------------------------------------------------------------------
// Substrat
// ---------------------------------------------------------------------------------------------

// La puce « Substrat » du flow résume matériau + épaisseur : on la tient à jour à la frappe.
["substrate-material", "substrate-width", "substrate-width-unit", "substrate-thickness", "substrate-thickness-unit"].forEach((id) => {
  document.getElementById(id).addEventListener("input", () => renderRail());
});

// ---------------------------------------------------------------------------------------------
// Sélection multiple
// ---------------------------------------------------------------------------------------------

function renderMultiInspector() {
  showInspectorSection("group-brick-wrap");
  const indices = [...state.selectedStepIndices].sort((a, b) => a - b);
  document.getElementById("group-brick-count").textContent = `${indices.length} étapes sélectionnées`;
  const contiguous = indices.every((idx, k) => k === 0 || idx === indices[k - 1] + 1);
  const alreadyGrouped = indices.some((idx) => state.steps[idx] && state.steps[idx].brick_group_id);
  const help = document.getElementById("group-brick-help");
  const btn = document.getElementById("group-brick-btn");
  btn.disabled = !contiguous || alreadyGrouped;
  help.textContent = !contiguous
    ? "Les étapes doivent être consécutives pour former une brique (Maj+clic sélectionne une plage)."
    : alreadyGrouped
      ? "Une de ces étapes appartient déjà à une brique - dissociez-la d'abord."
      : `Étapes ${indices[0] + 1} à ${indices[indices.length - 1] + 1} - la brique est enregistrée dans la bibliothèque du µprojet et reste réutilisable ailleurs.`;
}

document.getElementById("group-brick-btn").addEventListener("click", groupSelectionIntoBrick);
document.getElementById("group-brick-name").addEventListener("keydown", (e) => {
  if (e.key === "Enter") groupSelectionIntoBrick();
});
document.getElementById("delete-selection-btn").addEventListener("click", () => deleteSteps([...state.selectedStepIndices]));
document.getElementById("clear-selection-btn").addEventListener("click", clearMultiSelection);

// ---------------------------------------------------------------------------------------------
// Brique
// ---------------------------------------------------------------------------------------------

function renderBrickGroupInspector() {
  showInspectorSection("brick-group-section");
  const groupId = state.selectedBrickGroup;
  const [start, end] = brickGroupSpan(groupId);
  document.getElementById("brick-group-title").textContent = state.steps[start].brick_name || "Brique";
  const list = document.getElementById("brick-group-steps");
  const rows = [];
  for (let k = start; k <= end; k++) {
    const step = state.steps[k];
    rows.push(`
      <button class="sb-brick-step" type="button" data-index="${k}">
        ${stepIconHtml(step.kind)}
        <span class="sb-brick-step__body">
          <span class="sb-brick-step__name">${k + 1}. ${escapeHtml(step.name)}</span>
          <span class="sb-brick-step__sub">${escapeHtml(stepSummary(step))}</span>
        </span>
      </button>`);
  }
  list.innerHTML = rows.join("");
  list.querySelectorAll(".sb-brick-step").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.collapsedBrickGroups.delete(groupId);
      selectStep(parseInt(btn.dataset.index, 10));
    });
  });
  document.getElementById("brick-group-toggle-btn").textContent = state.collapsedBrickGroups.has(groupId) ? "Déplier dans le flow" : "Replier dans le flow";
}

document.getElementById("brick-group-toggle-btn").addEventListener("click", () => {
  if (state.selectedBrickGroup) toggleBrickCollapse(state.selectedBrickGroup);
});
document.getElementById("brick-group-ungroup-btn").addEventListener("click", () => {
  if (state.selectedBrickGroup) ungroupBrick(state.selectedBrickGroup);
});
document.getElementById("brick-group-delete-btn").addEventListener("click", () => {
  if (state.selectedBrickGroup) deleteBrickGroup(state.selectedBrickGroup);
});
