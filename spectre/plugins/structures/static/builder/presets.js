/* Présets d'étape : une étape entière déjà réglée (ses champs, ses paramètres déclarés, son
   étiquette, la recette du procédé qu'elle nomme), insérée d'un clic depuis la palette - voir
   spectre/plugins/process_library/step_presets.py. L'étape insérée est une copie : elle garde
   seulement la trace de son préset (step.presetOrigin : id, nom, version), qui voyage avec le
   procédé ({index d'étape: origine}, preset_origins) - jamais un lien vivant.

   Dans l'inspecteur, une étape issue d'un préset dit si elle lui est restée conforme, si elle a
   été modifiée depuis ou si le préset a changé, et permet de le réappliquer ou de le mettre à jour ;
   toute étape peut être enregistrée comme nouveau préset. */

const PRESET_SCOPE_LABELS = { builtin: "intégré", shared: "partagé", microproject: "µprojet" };

function clonePlain(value) {
  return value == null ? value : JSON.parse(JSON.stringify(value));
}

function findStepPreset(id) {
  return state.stepPresets.find((p) => p.id === id) || null;
}

// L'étape qu'insère un préset, avec tout ce qu'il porte.
function stepFromPreset(preset) {
  const step = clonePlain(preset.step);
  if (preset.declared_params && preset.declared_params.length) step.declaredParams = clonePlain(preset.declared_params);
  if (preset.layer_label) step.layerLabel = clonePlain(preset.layer_label);
  const own = attachRecipes([step], preset.recipes)[0];
  own.presetOrigin = { id: preset.id, name: preset.name, version: preset.version || 1 };
  return own;
}

// Ce qui, d'une étape, est le contenu d'un préset (pour comparer l'une à l'autre).
function presetContentOf(step) {
  const { id, presetOrigin, brick_group_id, brick_name, brick_source, declaredParams, layerLabel, ownRecipe, ...fields } = step;
  // la place d'une étiquette (texte déplacé, point d'accroche posé) tient au dessin d'une structure,
  // pas à l'étape : hors du préset
  const label = layerLabel ? { text: layerLabel.text, values: layerLabel.values } : null;
  return { fields, declared: declaredParams || [], label, recipe: ownRecipe && ownRecipe.name === step.recipe ? ownRecipe : null };
}

// Le serveur écrit chaque champ d'une étape (un angle à 0, une liste vide, null), le formulaire
// seulement ceux qu'il montre : on compare sans les valeurs vides, clés triées.
function canonicalContent(value) {
  if (Array.isArray(value)) return value.map(canonicalContent);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value)
        .filter(([, v]) => !(v === null || v === undefined || v === 0 || v === "" || (Array.isArray(v) && !v.length) || (typeof v === "object" && v && !Array.isArray(v) && !Object.keys(v).length)))
        .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
        .map(([k, v]) => [k, canonicalContent(v)])
    );
  }
  return value;
}

function samePresetContent(a, b) {
  return JSON.stringify(canonicalContent(a)) === JSON.stringify(canonicalContent(b));
}

// "same" | "modified" | "outdated" (le préset a changé depuis) | "missing" (retiré, ou hors de portée)
function presetStatus(step) {
  if (!step || !step.presetOrigin) return null;
  const preset = findStepPreset(step.presetOrigin.id);
  if (!preset) return { state: "missing", preset: null };
  if ((preset.version || 1) !== step.presetOrigin.version) return { state: "outdated", preset };
  const original = presetContentOf({ ...stepFromPreset(preset), name: step.name });
  return { state: samePresetContent(presetContentOf(step), original) ? "same" : "modified", preset };
}

const PRESET_STATUS_TEXT = {
  same: "conforme au préset",
  modified: "modifiée depuis",
  outdated: "le préset a changé depuis",
  missing: "préset retiré ou introuvable",
};

// -- insertion ---------------------------------------------------------------------------------

function insertPresetAt(preset, at = defaultInsertIndex()) {
  if (state.wizardScreen !== "structure" || !preset) return;
  clearError();
  const [step] = reconcileOwnRecipes([stepFromPreset(preset)]);
  const groupId = brickGroupInsideGap(at);
  if (groupId) {
    step.brick_group_id = groupId;
    step.brick_name = state.steps[at].brick_name;
    if (state.steps[at].brick_source) step.brick_source = state.steps[at].brick_source;
  }
  insertSteps(at, [step]);
}

// -- transport ---------------------------------------------------------------------------------

function presetOriginsPayload(steps) {
  const out = {};
  steps.forEach((step, i) => {
    if (step.presetOrigin) out[i] = step.presetOrigin;
  });
  return out;
}

function attachPresetOrigins(steps, origins) {
  if (!origins) return steps;
  return steps.map((step, i) => {
    const origin = origins[i] || origins[String(i)];
    return origin ? { ...step, presetOrigin: clonePlain(origin) } : step;
  });
}

// Tout ce qu'un procédé, une structure ou une brique enregistrés rattachent à leurs étapes.
function attachStepExtras(steps, data) {
  const withExtras = attachPresetOrigins(
    attachRecipes(attachLayerLabels(attachDeclaredParams(steps, data.declared_params), data.layer_labels), data.recipes),
    data.preset_origins
  );
  return attachBricks(withExtras, data.bricks);
}

// -- palette -----------------------------------------------------------------------------------

function renderPresetList() {
  const list = document.getElementById("insert-preset-list");
  if (!list) return;
  const search = document.getElementById("preset-search");
  const filter = search.value.trim().toLowerCase();
  const presets = state.stepPresets;
  search.hidden = presets.length < 6;
  const shown = presets.filter((p) => !filter || p.name.toLowerCase().includes(filter) || (STEP_KIND_DEFS[p.step.kind] || {}).label.toLowerCase().includes(filter));
  if (!presets.length) {
    list.innerHTML = `<div class="help">Aucun préset. Réglez une étape puis « Enregistrer comme préset » dans l'inspecteur.</div>`;
    return;
  }
  if (!shown.length) {
    list.innerHTML = `<div class="help">Aucun préset ne correspond.</div>`;
    return;
  }
  list.innerHTML = shown
    .map((p) => {
      const def = STEP_KIND_DEFS[p.step.kind];
      return `
        <button class="sb-preset-tool" type="button" draggable="true" data-id="${escapeHtml(p.id)}"
                title="${escapeHtml(p.name)}${p.notes ? ` - ${escapeHtml(p.notes)}` : ""}&#10;${escapeHtml(def ? def.label : p.step.kind)} · clic : insérer après la sélection · glisser : dans le flow">
          ${toolIconHtml(p.step.kind, 13)}
          <span class="sb-preset-tool__body">
            <span class="sb-preset-tool__name">${escapeHtml(p.name)}</span>
            <span class="sb-preset-tool__meta">${escapeHtml(def ? def.label : p.step.kind)} · ${PRESET_SCOPE_LABELS[p.scope] || p.scope}</span>
          </span>
        </button>`;
    })
    .join("");
}

(function wirePresetPalette() {
  const list = document.getElementById("insert-preset-list");
  if (!list) return;
  list.addEventListener("click", (event) => {
    const btn = event.target.closest(".sb-preset-tool");
    if (btn) insertPresetAt(findStepPreset(btn.dataset.id));
  });
  list.addEventListener("dragstart", (event) => {
    const btn = event.target.closest(".sb-preset-tool");
    const preset = btn && findStepPreset(btn.dataset.id);
    if (preset) startFlowDrag(event, { type: "preset", preset });
  });
  document.getElementById("preset-search").addEventListener("input", renderPresetList);
})();

// -- inspecteur --------------------------------------------------------------------------------

// Les paramètres d'une étape qu'un préset peut proposer de faire varier : ceux de l'écran des
// variations (variations.js), sans les dérivés (taux d'un nitrure, réseau d'une lithographie).
function presetVariableOptions(step) {
  const index = state.steps.indexOf(step);
  if (index === -1) return [];
  return variableParams(index).filter((p) => !p.field.includes("."));
}

function variableFieldsHtml(step, chosen, name) {
  const options = presetVariableOptions(step);
  if (!options.length) return `<div class="help" style="margin:0;">Aucun paramètre variable pour ce type d'étape.</div>`;
  return options
    .map(
      (o) =>
        `<label class="sb-check"><input type="checkbox" class="js-preset-variable" name="${name}" value="${escapeHtml(o.field)}" ${chosen.includes(o.field) ? "checked" : ""}> ${escapeHtml(o.label)}${o.declared ? " (déclaré)" : ""}</label>`
    )
    .join("");
}

function presetOriginHtml(step) {
  const status = presetStatus(step);
  if (!status) return "";
  const { preset } = status;
  const canUpdate = preset && preset.can_edit && status.state !== "same";
  const canReapply = preset && status.state !== "same";
  return `
    <div class="sb-preset-origin">
      <div class="sb-preset-origin__line">
        <span class="sb-preset-origin__name">Préset « ${escapeHtml(step.presetOrigin.name)} » · v${step.presetOrigin.version}</span>
        <span class="sb-preset-origin__status is-${status.state}" id="preset-status">${PRESET_STATUS_TEXT[status.state]}${status.state === "outdated" ? ` (v${preset.version})` : ""}</span>
      </div>
      <div class="sb-preset-origin__actions">
        ${canReapply ? `<button class="btn btn-line" type="button" id="preset-reapply-btn" title="Remet l'étape telle que le préset la décrit aujourd'hui">Réappliquer le préset</button>` : ""}
        ${canUpdate ? `<button class="btn btn-line" type="button" id="preset-update-btn" title="Enregistre cette étape dans le préset (nouvelle version) - sans toucher aux structures déjà construites">Mettre à jour le préset</button>` : ""}
        <button class="btn btn-line" type="button" id="preset-detach-btn" title="Oublier d'où vient cette étape">Détacher</button>
      </div>
    </div>`;
}

function savePresetFormHtml(step) {
  const canShare = true;
  return `
    <details class="sb-declared" id="preset-save-section">
      <summary class="sb-declared__summary">Enregistrer comme préset <span class="sb-declared__count">bibliothèque</span></summary>
      <div class="sb-declared__body sb-preset-save">
        <div><label for="preset-save-name">Nom du préset</label><input class="field" id="preset-save-name" maxlength="200" value="${escapeHtml(step.name)}" autocomplete="off"></div>
        <div><label for="preset-save-notes">Notes (optionnel)</label><input class="field" id="preset-save-notes" placeholder="À quoi il sert, quand l'utiliser…" autocomplete="off"></div>
        <fieldset class="sb-layer-label__values">
          <legend>Paramètres à faire varier ensuite</legend>
          <div class="sb-preset-save__variables">${variableFieldsHtml(step, [], "preset-save-variable")}</div>
        </fieldset>
        ${canShare ? `<label class="sb-check"><input type="checkbox" id="preset-save-shared"> Partagé avec tous les µprojets</label>` : ""}
        <button class="btn btn-primary btn-block" type="button" id="preset-save-btn">Enregistrer le préset</button>
        <div class="help" style="margin:0;">Tout ce que porte l'étape : ses champs, ses paramètres déclarés, son étiquette${step.ownRecipe ? ", sa recette du procédé" : ""}.</div>
      </div>
    </details>`;
}

// Le corps d'un préset depuis une étape (le nom de l'étape suit celui du préset).
function presetBodyFromStep(step) {
  const content = presetContentOf(step);
  return {
    step: content.fields,
    declared_params: content.declared,
    layer_label: content.label,
    recipes: processRecipesPayload([step]),
  };
}

function renderPresetPanel() {
  const panel = document.getElementById("step-preset-panel");
  if (!panel) return;
  const step = state.steps[state.selectedIndex];
  if (!step || isPresetMode) {
    panel.innerHTML = isPresetMode && step ? presetModeVariablesHtml(step) : "";
    return;
  }
  panel.innerHTML = presetOriginHtml(step) + savePresetFormHtml(step);
}

// Après une modification de l'étape : seul le statut change (le formulaire « enregistrer » garde
// ce qu'on y tape).
function refreshPresetStatus() {
  if (isPresetMode) {
    refreshPresetModeVariables();
    return;
  }
  const step = state.steps[state.selectedIndex];
  const holder = document.querySelector("#step-preset-panel .sb-preset-origin");
  const status = presetStatus(step);
  if (!holder || !status) return;
  const fresh = document.createElement("div");
  fresh.innerHTML = presetOriginHtml(step);
  holder.replaceWith(fresh.firstElementChild);
}

function replaceSelectedStep(step) {
  const i = state.selectedIndex;
  const previous = state.steps[i];
  if (previous.id) step.id = previous.id;
  ["brick_group_id", "brick_name", "brick_source"].forEach((key) => {
    if (previous[key]) step[key] = previous[key];
  });
  state.steps[i] = step;
  invalidateVariations();
  commitStructure();
  captureHistory();
}

document.getElementById("step-preset-panel").addEventListener("click", async (event) => {
  const step = state.steps[state.selectedIndex];
  if (!step) return;
  const status = presetStatus(step);
  if (event.target.closest("#preset-reapply-btn") && status && status.preset) {
    replaceSelectedStep({ ...stepFromPreset(status.preset), name: step.name });
  } else if (event.target.closest("#preset-detach-btn")) {
    const { presetOrigin, ...rest } = step;
    replaceSelectedStep(rest);
  } else if (event.target.closest("#preset-update-btn") && status && status.preset) {
    clearError();
    try {
      const updated = await processLibraryApi.updateStepPreset(status.preset.id, { ...presetBodyFromStep(step), step: { ...presetContentOf(step).fields, name: status.preset.step.name } });
      state.stepPresets = state.stepPresets.map((p) => (p.id === updated.id ? updated : p));
      step.presetOrigin = { id: updated.id, name: updated.name, version: updated.version };
      renderPresetPanel();
      renderPresetList();
      renderRail();
    } catch (err) {
      showError(err);
    }
  } else if (event.target.closest("#preset-save-btn")) {
    await saveStepAsPreset(step);
  }
});

async function saveStepAsPreset(step) {
  clearError();
  const name = document.getElementById("preset-save-name").value.trim();
  if (!name) {
    showError(new Error("Donnez un nom au préset."));
    document.getElementById("preset-save-name").focus();
    return;
  }
  const variable = [...document.querySelectorAll('input[name="preset-save-variable"]:checked')].map((box) => box.value);
  const shared = document.getElementById("preset-save-shared");
  const body = presetBodyFromStep(step);
  try {
    const created = await processLibraryApi.createStepPreset({
      ...body,
      name,
      step: { ...body.step, name: step.name },
      variable_fields: variable,
      notes: document.getElementById("preset-save-notes").value.trim() || null,
      scope: shared && shared.checked ? "shared" : "microproject",
      microproject: slug,
    });
    state.stepPresets = [...state.stepPresets, created];
    step.presetOrigin = { id: created.id, name: created.name, version: created.version };
    renderPresetList();
    renderPresetPanel();
    renderRail();
  } catch (err) {
    showError(err);
  }
}

// Les paramètres que le préset propose de faire varier, en tête de l'écran des variations.
function presetSuggestedFields(step) {
  const preset = step && step.presetOrigin ? findStepPreset(step.presetOrigin.id) : null;
  return preset ? preset.variable_fields || [] : [];
}
