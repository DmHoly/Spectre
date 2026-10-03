/* Page dédiée aux présets d'étape : liste (intégrés / partagés / µprojet) + formulaire de
   création/édition. Un préset ne fait que préremplir une recette (voir structureforge.core.
   recipes) dans le formulaire d'étape du constructeur (structures/static/builder/) - il n'est jamais
   référencé par nom au moment de la simulation. */

const { slug } = routeParams("/microprojets/{slug}/presets-etapes");

const MODE_LABELS = { conformal: "conforme", directional: "directionnel", isotropic: "isotrope" };

const state = {
  presets: [],
  recipes: { deposition: [], etch: [] },
  editing: null, // le préset en cours de modification, ou null = création
};

const errorBox = document.getElementById("error");
function showError(err) {
  errorBox.textContent = err.message || String(err);
  errorBox.style.display = "block";
  document.getElementById("flash").style.display = "none";
}
function clearMessages() {
  errorBox.style.display = "none";
  document.getElementById("flash").style.display = "none";
}
function showFlash(message) {
  const flashBox = document.getElementById("flash");
  flashBox.textContent = message;
  flashBox.style.display = "block";
  errorBox.style.display = "none";
}

function recipeHint(kind, name) {
  const recipe = (state.recipes[kind] || []).find((r) => r.name === name);
  if (!recipe) return "";
  const mode = MODE_LABELS[recipe.mode] || recipe.mode;
  const angle = recipe.angle_deg ? ` (${recipe.angle_deg}°)` : "";
  return recipe.notes ? `${mode}${angle} — ${recipe.notes}` : `${mode}${angle}`;
}

function renderRecipeOptions() {
  const kind = document.getElementById("f-kind").value;
  const recipeSelect = document.getElementById("f-recipe");
  recipeSelect.innerHTML = (state.recipes[kind] || [])
    .map((r) => `<option value="${escapeHtml(r.name)}">${escapeHtml(r.name)}</option>`)
    .join("");
  updateRecipeHint();
}

function updateRecipeHint() {
  const kind = document.getElementById("f-kind").value;
  document.getElementById("f-recipe-hint").textContent = recipeHint(kind, document.getElementById("f-recipe").value);
}

document.getElementById("f-kind").addEventListener("change", renderRecipeOptions);
document.getElementById("f-recipe").addEventListener("change", updateRecipeHint);

function resetForm() {
  state.editing = null;
  document.getElementById("preset-form").reset();
  renderRecipeOptions();
  document.getElementById("form-title").textContent = "Nouveau préset";
  document.getElementById("submit-btn").textContent = "Créer le préset";
  document.getElementById("cancel-edit-btn").style.display = "none";
  // Arrivée depuis le hub /bibliotheque (?partagee=1) : préset partagé par défaut.
  if (new URLSearchParams(window.location.search).get("partagee") === "1") {
    document.getElementById("f-scope").value = "shared";
  }
}

document.getElementById("cancel-edit-btn").addEventListener("click", resetForm);

function scopeSuffix(scope) {
  if (scope === "builtin") return `<span style="font-weight:400;font-size:11px;color:var(--text-faint);">· intégré, disponible dans tous les µprojets</span>`;
  if (scope === "shared") return `<span style="font-weight:400;font-size:11px;color:var(--text-faint);">· partagé, visible dans tous les µprojets</span>`;
  return "";
}

function recipeSummary(payload) {
  const kindLabel = payload.kind === "etch" ? "Gravure" : "Dépôt";
  return `${kindLabel} · ${escapeHtml(payload.recipe)}`;
}

function presetRow(preset) {
  const canCreate = state.currentRole === "editor" || state.currentRole === "owner";
  return `
    <div class="step-row" style="align-items:flex-start;">
      <div style="flex:1;min-width:0;">
        <div style="font-size:13px;font-weight:600;">${escapeHtml(preset.name)} ${scopeSuffix(preset.scope)}</div>
        <div style="font-size:12px;color:var(--text-faint);">${recipeSummary(preset.payload)}</div>
        ${preset.notes ? `<div style="font-size:12px;color:var(--text-soft);margin-top:3px;max-width:56ch;">${escapeHtml(preset.notes)}</div>` : ""}
      </div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end;">
        ${canCreate ? `<button class="btn btn-line js-duplicate" data-id="${escapeHtml(preset.id)}" type="button" style="padding:5px 10px;font-size:12px;">Dupliquer</button>` : ""}
        ${
          preset.can_edit
            ? `<button class="btn btn-line js-edit" data-id="${escapeHtml(preset.id)}" type="button" style="padding:5px 10px;font-size:12px;">Modifier</button>`
            : ""
        }
        ${
          preset.can_edit
            ? `<button class="btn btn-line js-remove" data-id="${escapeHtml(preset.id)}" type="button" style="padding:5px 10px;font-size:12px;color:var(--danger);">Supprimer</button>`
            : ""
        }
      </div>
    </div>`;
}

function findPreset(id) {
  return state.presets.find((p) => p.id === id) || null;
}

function fillFormFrom(preset, { asDuplicate } = {}) {
  document.getElementById("f-name").value = asDuplicate ? `${preset.name} (copie)` : preset.name;
  document.getElementById("f-kind").value = preset.payload.kind;
  renderRecipeOptions();
  document.getElementById("f-recipe").value = preset.payload.recipe;
  updateRecipeHint();
  document.getElementById("f-notes").value = preset.notes || "";
  document.getElementById("f-scope").value = !asDuplicate && preset.scope === "shared" ? "shared" : "microproject";
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function confirmRemoval(preset) {
  const shared = preset.scope === "shared" ? " Il est partagé : il disparaîtra de tous les µprojets." : "";
  return window.confirm(`Supprimer le préset « ${preset.name} » ?${shared}`);
}

function renderList() {
  document.getElementById("presets-list").innerHTML = state.presets.length
    ? state.presets.map(presetRow).join("")
    : `<div class="help">Aucun préset pour l'instant.</div>`;

  document.querySelectorAll(".js-duplicate").forEach((btn) => {
    btn.addEventListener("click", () => {
      const preset = findPreset(btn.dataset.id);
      if (!preset) return;
      resetForm();
      fillFormFrom(preset, { asDuplicate: true });
    });
  });
  document.querySelectorAll(".js-edit").forEach((btn) => {
    btn.addEventListener("click", () => {
      const preset = findPreset(btn.dataset.id);
      if (!preset) return;
      state.editing = preset;
      document.querySelector(".card.card-pad").style.display = "";
      fillFormFrom(preset, { asDuplicate: false });
      document.getElementById("form-title").textContent = "Modifier le préset";
      document.getElementById("submit-btn").textContent = "Enregistrer les modifications";
      document.getElementById("cancel-edit-btn").style.display = "";
    });
  });
  document.querySelectorAll(".js-remove").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const preset = findPreset(btn.dataset.id);
      if (!preset || !confirmRemoval(preset)) return;
      try {
        await processLibraryApi.deleteStepPreset(preset.id);
        if (state.editing && state.editing.id === preset.id) resetForm();
        await loadPresets();
        showFlash("Préset supprimé.");
      } catch (err) {
        showError(err);
      }
    });
  });
}

async function loadPresets() {
  state.presets = await processLibraryApi.stepPresets({ microproject: slug });
  renderList();
}

document.getElementById("preset-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  clearMessages();
  const kind = document.getElementById("f-kind").value;
  const body = {
    name: document.getElementById("f-name").value.trim(),
    payload: { kind, recipe: document.getElementById("f-recipe").value },
    notes: document.getElementById("f-notes").value.trim() || null,
    scope: document.getElementById("f-scope").value,
    microproject: slug,
  };
  try {
    if (state.editing) {
      await processLibraryApi.updateStepPreset(state.editing.id, body);
      showFlash("Préset mis à jour.");
    } else {
      await processLibraryApi.createStepPreset(body);
      showFlash("Préset créé.");
    }
    resetForm();
    await loadPresets();
  } catch (err) {
    showError(err);
  }
});

async function init() {
  try {
    const microproject = await microprojectsApi.get(slug);
    state.currentRole = microproject.role;
    document.getElementById("crumb").textContent = "/ " + microproject.name;
    document.getElementById("back-link").href = "/bibliotheque";
    if (!(state.currentRole === "editor" || state.currentRole === "owner")) {
      document.querySelector(".card.card-pad").style.display = "none";
    }
  } catch (err) {
    showError(err);
    return;
  }
  try {
    state.recipes = await structuresApi.listRecipes();
  } catch (err) {
    state.recipes = { deposition: [], etch: [] };
  }
  renderRecipeOptions();
  try {
    await loadPresets();
  } catch (err) {
    showError(err);
  }
}

init();
