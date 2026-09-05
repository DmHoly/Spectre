/* Page dédiée aux présets d'étape : liste (présets intégrés / partagés / projet) + formulaire de
   création/édition. Un préset ne fait que préremplir une recette (voir structureforge.core.
   recipes) dans le formulaire d'étape du constructeur (js/structure-builder/) - il n'est jamais
   référencé par nom au moment de la simulation. */

const pathParts = window.location.pathname.split("/").filter(Boolean);
const slug = pathParts[1];

const MODE_LABELS = { conformal: "conforme", directional: "directionnel", isotropic: "isotrope" };

const state = {
  presets: { presets: [], partagees: [], projet: [] },
  recipes: { deposition: [], etch: [] },
  editing: null, // { name, partagee } of the preset currently being edited, or null = creating
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
}

document.getElementById("cancel-edit-btn").addEventListener("click", resetForm);

function scopeSuffix(scope) {
  if (scope === "preset") return `<span style="font-weight:400;font-size:11px;color:var(--text-faint);">· préset, disponible dans tous les projets</span>`;
  if (scope === "partagee") return `<span style="font-weight:400;font-size:11px;color:var(--text-faint);">· partagée, visible dans tous les projets</span>`;
  return "";
}

function recipeSummary(payload) {
  const kindLabel = payload.kind === "etch" ? "Gravure" : "Dépôt";
  return `${kindLabel} · ${payload.recipe}`;
}

function presetRow(preset) {
  const canManage = state.currentRole === "editor" || state.currentRole === "owner";
  const isPreset = preset.scope === "preset";
  return `
    <div class="step-row" style="align-items:flex-start;">
      <div style="flex:1;min-width:0;">
        <div style="font-size:13px;font-weight:600;">${escapeHtml(preset.name)} ${scopeSuffix(preset.scope)}</div>
        <div style="font-size:12px;color:var(--text-faint);">${recipeSummary(preset.payload)}</div>
        ${preset.notes ? `<div style="font-size:12px;color:var(--text-soft);margin-top:3px;max-width:56ch;">${escapeHtml(preset.notes)}</div>` : ""}
      </div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end;">
        ${canManage ? `<button class="btn btn-line js-duplicate" data-name="${escapeHtml(preset.name)}" data-scope="${preset.scope}" type="button" style="padding:5px 10px;font-size:12px;">Dupliquer</button>` : ""}
        ${
          canManage && !isPreset
            ? `<button class="btn btn-line js-edit" data-name="${escapeHtml(preset.name)}" data-scope="${preset.scope}" type="button" style="padding:5px 10px;font-size:12px;">Modifier</button>`
            : ""
        }
        ${
          canManage && !isPreset
            ? `<button class="btn btn-line js-remove" data-name="${escapeHtml(preset.name)}" data-scope="${preset.scope}" type="button" style="padding:5px 10px;font-size:12px;color:var(--danger);">Supprimer</button>`
            : ""
        }
      </div>
    </div>`;
}

function findPreset(scope, name) {
  const bucket = scope === "preset" ? state.presets.presets : scope === "partagee" ? state.presets.partagees : state.presets.projet;
  return (bucket || []).find((p) => p.name === name) || null;
}

function fillFormFrom(preset, { asDuplicate } = {}) {
  document.getElementById("f-name").value = asDuplicate ? `${preset.name} (copie)` : preset.name;
  document.getElementById("f-kind").value = preset.payload.kind;
  renderRecipeOptions();
  document.getElementById("f-recipe").value = preset.payload.recipe;
  updateRecipeHint();
  document.getElementById("f-notes").value = preset.notes || "";
  document.getElementById("f-partagee").value = asDuplicate ? "false" : preset.scope === "partagee" ? "true" : "false";
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderList() {
  const entries = [
    ...state.presets.presets.map((p) => ({ ...p, scope: "preset" })),
    ...state.presets.partagees.map((p) => ({ ...p, scope: "partagee" })),
    ...state.presets.projet.map((p) => ({ ...p, scope: "projet" })),
  ];
  document.getElementById("presets-list").innerHTML = entries.length
    ? entries.map(presetRow).join("")
    : `<div class="help">Aucun préset pour l'instant.</div>`;

  document.querySelectorAll(".js-duplicate").forEach((btn) => {
    btn.addEventListener("click", () => {
      const preset = findPreset(btn.dataset.scope, btn.dataset.name);
      if (!preset) return;
      resetForm();
      fillFormFrom(preset, { asDuplicate: true });
    });
  });
  document.querySelectorAll(".js-edit").forEach((btn) => {
    btn.addEventListener("click", () => {
      const preset = findPreset(btn.dataset.scope, btn.dataset.name);
      if (!preset) return;
      state.editing = { name: preset.name, partagee: btn.dataset.scope === "partagee" };
      fillFormFrom(preset, { asDuplicate: false });
      document.getElementById("form-title").textContent = "Modifier le préset";
      document.getElementById("submit-btn").textContent = "Enregistrer les modifications";
      document.getElementById("cancel-edit-btn").style.display = "";
    });
  });
  document.querySelectorAll(".js-remove").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        state.presets = await api.del(
          `/api/projects/${encodeURIComponent(slug)}/presets-etapes/${encodeURIComponent(btn.dataset.name)}?partagee=${btn.dataset.scope === "partagee"}`
        );
        if (state.editing && state.editing.name === btn.dataset.name) resetForm();
        renderList();
        showFlash("Préset supprimé.");
      } catch (err) {
        showError(err);
      }
    });
  });
}

async function loadPresets() {
  state.presets = await api.get(`/api/projects/${encodeURIComponent(slug)}/presets-etapes`);
  renderList();
}

document.getElementById("preset-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  clearMessages();
  const kind = document.getElementById("f-kind").value;
  const payload = { kind, recipe: document.getElementById("f-recipe").value };
  const body = {
    name: document.getElementById("f-name").value.trim(),
    payload,
    notes: document.getElementById("f-notes").value.trim() || null,
    partagee: document.getElementById("f-partagee").value === "true",
  };
  try {
    if (state.editing) {
      state.presets = await api.put(
        `/api/projects/${encodeURIComponent(slug)}/presets-etapes/${encodeURIComponent(state.editing.name)}?partagee=${state.editing.partagee}`,
        body
      );
      showFlash("Préset mis à jour.");
    } else {
      state.presets = await api.post(`/api/projects/${encodeURIComponent(slug)}/presets-etapes`, body);
      showFlash("Préset créé.");
    }
    resetForm();
    renderList();
  } catch (err) {
    showError(err);
  }
});

async function init() {
  try {
    const project = await api.get(`/api/projects/${encodeURIComponent(slug)}`);
    state.currentRole = project.role;
    document.getElementById("crumb").textContent = "/ " + project.name;
    document.getElementById("back-link").href = `/projets/${encodeURIComponent(slug)}`;
    if (!(state.currentRole === "editor" || state.currentRole === "owner")) {
      document.querySelector(".card.card-pad").style.display = "none";
    }
  } catch (err) {
    showError(err);
    return;
  }
  try {
    state.recipes = await api.get(`/api/projects/${encodeURIComponent(slug)}/recettes`);
  } catch (err) {
    state.recipes = { deposition: [], etch: [] };
  }
  renderRecipeOptions();
  loadPresets();
}

init();
