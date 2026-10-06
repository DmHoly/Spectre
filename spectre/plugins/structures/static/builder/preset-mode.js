/* Mode préset : régler un préset d'étape dans le constructeur - une seule étape, avec tous les
   formulaires des étapes (recette du procédé, paramètres déclarés, étiquette), plus les paramètres
   que le préset proposera de faire varier. Même mécanique que le mode brique (brick-mode.js) : le
   substrat ne sert qu'à prévisualiser l'étape, il n'est jamais enregistré avec le préset. */

document.getElementById("preset-save-mode-btn").addEventListener("click", () => saveStepPreset(false));
document.getElementById("preset-save-as-mode-btn").addEventListener("click", () => saveStepPreset(true));

function presetModeVariablesHtml(step) {
  const options = presetVariableOptions(step);
  state.presetVariableFields = state.presetVariableFields.filter((field) => options.some((o) => o.field === field));
  return `
    <div class="sb-preset-mode" data-options="${escapeHtml(options.map((o) => o.field).join("|"))}">
      <fieldset class="sb-layer-label__values">
        <legend>Paramètres que le préset proposera de faire varier</legend>
        <div class="sb-preset-save__variables">${variableFieldsHtml(step, state.presetVariableFields, "preset-mode-variable")}</div>
      </fieldset>
      <div class="help" style="margin:0;">Ils viennent en tête quand on prépare une campagne sur une étape issue de ce préset.</div>
    </div>`;
}

// Les cases suivent l'étape : un paramètre déclaré ajouté devient proposable.
function refreshPresetModeVariables() {
  const holder = document.querySelector("#step-preset-panel .sb-preset-mode");
  const step = state.steps[state.selectedIndex];
  if (!holder || !step) return;
  const key = presetVariableOptions(step)
    .map((o) => o.field)
    .join("|");
  if (holder.dataset.options !== key) renderPresetPanel();
}

document.getElementById("step-preset-panel").addEventListener("change", (event) => {
  const box = event.target.closest('input[name="preset-mode-variable"]');
  if (!box) return;
  state.presetVariableFields = [...document.querySelectorAll('input[name="preset-mode-variable"]:checked')].map((b) => b.value);
});

async function saveStepPreset(forceNew) {
  clearError();
  const name = document.getElementById("preset-name").value.trim();
  if (!name) {
    showError(new Error("Donnez un nom à ce préset pour l'enregistrer."));
    document.getElementById("preset-name").focus();
    return;
  }
  if (state.steps.length !== 1) {
    showError(
      new Error(
        state.steps.length
          ? "Un préset est une seule étape - pour une séquence, enregistrez une brique technologique."
          : "Ajoutez l'étape du préset depuis la palette avant de l'enregistrer."
      )
    );
    return;
  }
  const step = state.steps[0];
  const payload = {
    ...presetBodyFromStep(step),
    name,
    variable_fields: state.presetVariableFields,
    notes: document.getElementById("preset-notes").value.trim() || null,
    scope: document.getElementById("preset-shared-checkbox").checked ? "shared" : "microproject",
    microproject: slug,
  };
  try {
    if (!forceNew && state.editingPresetId) {
      await processLibraryApi.updateStepPreset(state.editingPresetId, payload);
    } else {
      await processLibraryApi.createStepPreset(payload);
    }
    window.location.href = returnTo === "bibliotheque" ? "/bibliotheque" : `/microprojets/${slug}/presets-etapes`;
  } catch (err) {
    showError(err);
  }
}

async function initPresetMode() {
  document.getElementById("preset-header").hidden = false;
  document.getElementById("preset-save-mode-btn").hidden = false;
  document.getElementById("preset-preview-note").hidden = false;
  document.getElementById("palette-bricks").hidden = true;
  if (queryParams.get("partagee") === "1") document.getElementById("preset-shared-checkbox").checked = true;

  if (!presetId) {
    setPageTitle("Nouveau préset d'étape");
    const kind = queryParams.get("type");
    if (kind && STEP_KIND_DEFS[kind]) insertStepOfKind(kind, 0);
    document.getElementById("preset-name").focus();
    return;
  }
  try {
    const found = await processLibraryApi.stepPreset(presetId);
    const { presetOrigin, ...step } = stepFromPreset(found); // on règle le préset lui-même
    state.steps = [step];
    state.presetVariableFields = [...(found.variable_fields || [])];
    selectLastStep();
    renderSteps();
    document.getElementById("preset-notes").value = found.notes || "";
    // un préset intégré (ou qu'on ne peut pas modifier) n'a rien à éditer en place
    if (libraryDuplicateMode || !found.can_edit) {
      setPageTitle(found.scope === "builtin" ? "Enregistrer ce préset sous un nouveau nom" : "Dupliquer un préset");
      document.getElementById("preset-name").value = `${found.name} (copie)`;
    } else {
      setPageTitle("Modifier le préset");
      document.getElementById("preset-name").value = found.name;
      document.getElementById("preset-shared-checkbox").checked = found.scope === "shared";
      document.getElementById("preset-version").textContent = `version ${found.version}`;
      document.getElementById("preset-version").hidden = false;
      state.editingPresetId = found.id;
      document.getElementById("preset-save-as-mode-btn").hidden = false;
    }
  } catch (err) {
    showError(err);
  }
}
