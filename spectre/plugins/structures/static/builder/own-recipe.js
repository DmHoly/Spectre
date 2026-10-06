/* Recettes propres au procédé : un dépôt ou une gravure dont on écrit soi-même le mode, l'angle et,
   pour une gravure, la sélectivité (une gravure sélective de l'Al2O3, un etch back qui s'arrête sur
   le GaN...), sans passer par la bibliothèque racine (recettes.yml). Une étape la nomme comme
   n'importe quelle recette ; elle vit sur l'étape (step.ownRecipe) et voyage dans l'API avec le
   procédé ({deposition: [...], etch: [...]}, voir simulation.ProcessRecipes côté serveur) - une
   modification de la bibliothèque ne change donc jamais un procédé qui a défini la sienne. Deux
   étapes qui nomment la même recette du procédé la partagent : la modifier depuis l'une la change
   pour toutes. */

const OWN_RECIPE_KINDS = new Set(["deposition", "etch"]);
const NEW_RECIPE_VALUE = "__new_recipe__";
const OWN_RECIPE_MODES = {
  deposition: [
    ["conformal", "Conforme (CVD, ALD) - épaisseur égale sur toute surface exposée"],
    ["directional", "Directionnel (PVD, évaporation) - suit un angle"],
  ],
  etch: [
    ["isotropic", "Isotrope (humide) - grave dans toutes les directions"],
    ["directional", "Directionnel (RIE, usinage ionique) - suit un angle"],
  ],
};
const SELECTIVITY_CATEGORIES = ["semiconductor", "dielectric", "metal", "resist", "substrate", "other"];

function cloneRecipe(recipe) {
  return recipe ? JSON.parse(JSON.stringify(recipe)) : null;
}

// Les recettes du procédé d'un type : celles des étapes, et celle du formulaire ouvert (pas encore
// reportée sur son étape) - la plus récente l'emporte pour un même nom.
function ownRecipes(kind) {
  const byName = new Map();
  state.steps.forEach((step) => {
    if (step.kind === kind && step.ownRecipe) byName.set(step.ownRecipe.name, step.ownRecipe);
  });
  if (state.formOwnRecipe && state.formOwnRecipeKind === kind) byName.set(state.formOwnRecipe.name, state.formOwnRecipe);
  return byName;
}

function libraryRecipe(kind, name) {
  return (state.recipes[kind] || []).find((r) => r.name === name) || null;
}

function uniqueRecipeName(kind, base) {
  const taken = new Set([...(state.recipes[kind] || []).map((r) => r.name), ...ownRecipes(kind).keys()]);
  if (!taken.has(base)) return base;
  let n = 2;
  while (taken.has(`${base} (${n})`)) n++;
  return `${base} (${n})`;
}

function blankRecipe(kind) {
  const name = uniqueRecipeName(kind, kind === "etch" ? "Gravure du procédé" : "Dépôt du procédé");
  return kind === "etch"
    ? { name, mode: "isotropic", angle_deg: 0, selectivity_by_material: {}, selectivity_by_category: {}, default_factor: 1, notes: null }
    : { name, mode: "conformal", angle_deg: 0, notes: null };
}

function customizedRecipe(kind, name) {
  const base = libraryRecipe(kind, name);
  if (!base) return blankRecipe(kind);
  return { ...cloneRecipe(base), name: uniqueRecipeName(kind, `${name} (procédé)`) };
}

// Les options du <select> de recette : la bibliothèque, puis les recettes du procédé, puis « Nouvelle… ».
function recipeSelectOptionsHtml(kind) {
  const own = [...ownRecipes(kind).keys()];
  const ownGroup = own.length
    ? `<optgroup label="Recettes de ce procédé">${own.map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join("")}</optgroup>`
    : "";
  return (
    `<optgroup label="Bibliothèque">${recipeOptions(kind)}</optgroup>` +
    ownGroup +
    `<option value="${NEW_RECIPE_VALUE}">＋ Nouvelle recette du procédé…</option>`
  );
}

function ownRecipePanelHtml(kind) {
  const recipe = state.formOwnRecipe;
  if (!recipe) {
    return `<button class="btn btn-line btn-block" type="button" id="f-own-customize" style="margin-top:6px;">Personnaliser cette recette pour ce procédé</button>`;
  }
  const modes = OWN_RECIPE_MODES[kind]
    .map(([value, label]) => `<option value="${value}" ${recipe.mode === value ? "selected" : ""}>${escapeHtml(label)}</option>`)
    .join("");
  const etchFields =
    kind === "etch"
      ? `
      <div>
        <label for="f-own-default">Vitesse relative de tout autre matériau</label>
        <input class="field" id="f-own-default" type="number" min="0" step="0.05" value="${escapeHtml(formatNumberInput(recipe.default_factor ?? 1))}">
        <div class="help" style="margin-top:4px;">1 = vitesse nominale · 0 = non gravé (couche d'arrêt). Une gravure sélective : 0 ici, 1 sur le matériau visé.</div>
      </div>
      <fieldset class="sb-own-recipe__table">
        <legend>Par matériau</legend>
        <div id="f-own-rows">${Object.entries(recipe.selectivity_by_material || {}).map(([material, factor], i) => selectivityRowHtml(material, factor, i)).join("")}</div>
        <button class="btn btn-line btn-block" type="button" id="f-own-add-row">+ Ajouter un matériau</button>
        <datalist id="f-own-materials">${state.materials.map((m) => `<option value="${escapeHtml(m.name)}"></option>`).join("")}</datalist>
      </fieldset>
      <details class="sb-own-recipe__categories" ${Object.keys(recipe.selectivity_by_category || {}).length ? "open" : ""}>
        <summary>Par catégorie (vaut pour tout InGaN / AlGaN à composition)</summary>
        <div class="sb-own-recipe__grid">
          ${SELECTIVITY_CATEGORIES.map((category) => {
            const value = (recipe.selectivity_by_category || {})[category];
            return `<div><label for="f-own-cat-${category}">${escapeHtml(MATERIAL_CATEGORY_LABELS[category] || category)}</label><input class="field js-own-category" id="f-own-cat-${category}" data-category="${category}" type="number" min="0" step="0.05" value="${value == null ? "" : escapeHtml(formatNumberInput(value))}" placeholder="—"></div>`;
          }).join("")}
        </div>
        <div class="help" style="margin-top:4px;">Ordre de résolution : matériau, puis catégorie, puis la vitesse de tout autre matériau.</div>
      </details>`
      : "";
  return `
    <div class="sb-own-recipe" id="f-own-recipe-box">
      <div class="sb-own-recipe__title">Recette de ce procédé</div>
      <div><label for="f-own-name">Nom</label><input class="field" id="f-own-name" maxlength="120" value="${escapeHtml(recipe.name)}" autocomplete="off"></div>
      <div class="field-row">
        <div><label for="f-own-mode">Mode</label><select class="field" id="f-own-mode">${modes}</select></div>
        <div ${recipe.mode === "directional" ? "" : "hidden"} id="f-own-angle-wrap"><label for="f-own-angle">Angle (° depuis la verticale)</label><input class="field" id="f-own-angle" type="number" min="-89" max="89" step="1" value="${escapeHtml(formatNumberInput(recipe.angle_deg || 0))}"></div>
      </div>
      ${etchFields}
      <div class="help" style="margin:0;">Enregistrée avec le procédé : la bibliothèque peut changer, cette structure garde sa recette.</div>
    </div>`;
}

function selectivityRowHtml(material, factor, index) {
  return `
    <div class="sb-own-recipe__row js-own-row" data-index="${index}">
      <input class="field js-own-material" list="f-own-materials" value="${escapeHtml(material)}" placeholder="ex : Al2O3" aria-label="Matériau" autocomplete="off">
      <input class="field js-own-factor" type="number" min="0" step="0.05" value="${escapeHtml(formatNumberInput(factor))}" aria-label="Vitesse relative">
      <button class="btn btn-line js-own-remove" type="button" title="Retirer ce matériau" style="flex:none;">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 5l14 14M5 19L19 5"/></svg>
      </button>
    </div>`;
}

// La recette du formulaire telle que ses champs la décrivent (mutée en place, avant que le
// formulaire commun ne relise l'étape : ces écouteurs sont posés sur les champs eux-mêmes).
function readOwnRecipeFields() {
  const recipe = state.formOwnRecipe;
  const box = document.getElementById("f-own-recipe-box");
  if (!recipe || !box) return;
  recipe.name = document.getElementById("f-own-name").value.trim() || recipe.name;
  recipe.mode = document.getElementById("f-own-mode").value;
  recipe.angle_deg = recipe.mode === "directional" ? parseFloat(document.getElementById("f-own-angle").value) || 0 : 0;
  if (document.getElementById("f-own-default")) {
    const factor = parseFloat(document.getElementById("f-own-default").value);
    recipe.default_factor = Number.isFinite(factor) && factor >= 0 ? factor : 1;
    const byMaterial = {};
    box.querySelectorAll(".js-own-row").forEach((row) => {
      const material = row.querySelector(".js-own-material").value.trim();
      const value = parseFloat(row.querySelector(".js-own-factor").value);
      if (material) byMaterial[material] = Number.isFinite(value) && value >= 0 ? value : 0;
    });
    recipe.selectivity_by_material = byMaterial;
    const byCategory = {};
    box.querySelectorAll(".js-own-category").forEach((input) => {
      const value = parseFloat(input.value);
      if (input.value.trim() !== "" && Number.isFinite(value) && value >= 0) byCategory[input.dataset.category] = value;
    });
    recipe.selectivity_by_category = byCategory;
  }
  // le nom de la recette est aussi l'option choisie
  const select = document.getElementById("f-recipe");
  const option = select.options[select.selectedIndex];
  if (option && option.value !== recipe.name && option.parentElement.label === "Recettes de ce procédé") {
    option.value = recipe.name;
    option.textContent = recipe.name;
  }
}

function renderOwnRecipePanel(kind) {
  const slot = document.getElementById("f-own-recipe-slot");
  if (!slot) return;
  slot.innerHTML = ownRecipePanelHtml(kind);
  const customize = document.getElementById("f-own-customize");
  if (customize) {
    customize.addEventListener("click", () => {
      const select = document.getElementById("f-recipe");
      state.formOwnRecipe = customizedRecipe(kind, select.value);
      state.formOwnRecipeKind = kind;
      select.innerHTML = recipeSelectOptionsHtml(kind);
      select.value = state.formOwnRecipe.name;
      updateRecipeHint(kind);
      renderOwnRecipePanel(kind);
      livePreviewFromForm();
    });
    return;
  }
  const box = document.getElementById("f-own-recipe-box");
  box.addEventListener("input", readOwnRecipeFields);
  box.addEventListener("change", readOwnRecipeFields);
  document.getElementById("f-own-mode").addEventListener("change", (e) => {
    document.getElementById("f-own-angle-wrap").hidden = e.target.value !== "directional";
  });
  const addRow = document.getElementById("f-own-add-row");
  if (addRow) {
    addRow.addEventListener("click", () => {
      readOwnRecipeFields();
      const rows = document.getElementById("f-own-rows");
      rows.insertAdjacentHTML("beforeend", selectivityRowHtml("", 1, rows.children.length));
      rows.lastElementChild.querySelector(".js-own-material").focus();
    });
  }
  box.addEventListener("click", (e) => {
    const remove = e.target.closest(".js-own-remove");
    if (!remove) return;
    remove.closest(".js-own-row").remove();
    readOwnRecipeFields();
    livePreviewFromForm();
  });
}

function updateRecipeHint(kind) {
  const hint = document.getElementById("f-recipe-hint");
  const select = document.getElementById("f-recipe");
  if (!hint || !select) return;
  hint.textContent = state.formOwnRecipe ? "" : recipeHint(kind, select.value);
}

// Le champ « Recette » d'un dépôt ou d'une gravure : choisir une recette de la bibliothèque, une du
// procédé (sa définition s'ouvre dessous), ou en créer une.
function wireRecipeField(kind) {
  const select = document.getElementById("f-recipe");
  select.addEventListener("change", () => {
    if (select.value === NEW_RECIPE_VALUE) {
      state.formOwnRecipe = blankRecipe(kind);
      state.formOwnRecipeKind = kind;
      select.innerHTML = recipeSelectOptionsHtml(kind);
      select.value = state.formOwnRecipe.name;
    } else {
      const own = ownRecipes(kind).get(select.value);
      state.formOwnRecipe = own ? cloneRecipe(own) : null;
      state.formOwnRecipeKind = own ? kind : null;
    }
    updateRecipeHint(kind);
    renderOwnRecipePanel(kind);
  });
  updateRecipeHint(kind);
  renderOwnRecipePanel(kind);
}

// À l'ouverture d'un formulaire : la recette du procédé que nomme l'étape (null : une recette de la
// bibliothèque) - appelée avant le rendu des champs (inspector.js).
function setFormOwnRecipe(step) {
  state.formOwnRecipe = step && step.ownRecipe ? cloneRecipe(step.ownRecipe) : null;
  state.formOwnRecipeKind = state.formOwnRecipe ? step.kind : null;
}

// La recette que lit buildFromForm : celle du formulaire, si c'est elle que nomme le <select>.
function ownRecipeFromForm(recipeName) {
  return state.formOwnRecipe && state.formOwnRecipe.name === recipeName ? cloneRecipe(state.formOwnRecipe) : null;
}

// Une recette du procédé modifiée depuis une étape vaut pour toutes celles qui la nomment (un
// renommage compris) - appelée à chaque relecture du formulaire (inspector.js).
function shareOwnRecipe(edited, previousName) {
  if (!edited.ownRecipe) return;
  const names = new Set([previousName, edited.ownRecipe.name]);
  state.steps.forEach((step, i) => {
    if (step === edited || step.kind !== edited.kind || !step.ownRecipe || !names.has(step.recipe)) return;
    state.steps[i] = { ...step, recipe: edited.ownRecipe.name, ownRecipe: cloneRecipe(edited.ownRecipe) };
  });
}

// {deposition: [...], etch: [...]} à l'envoi : les recettes du procédé que nomment ces étapes.
function processRecipesPayload(steps) {
  const out = { deposition: [], etch: [] };
  const seen = { deposition: new Set(), etch: new Set() };
  steps.forEach((step) => {
    const recipe = step.ownRecipe;
    if (!recipe || !OWN_RECIPE_KINDS.has(step.kind) || step.recipe !== recipe.name || seen[step.kind].has(recipe.name)) return;
    seen[step.kind].add(recipe.name);
    out[step.kind].push(cloneRecipe(recipe));
  });
  return out;
}

// Au chargement d'un procédé, d'une structure, d'une brique ou d'un préset : chaque étape qui nomme
// une recette du procédé la porte.
function attachRecipes(steps, recipes) {
  if (!recipes) return steps;
  return steps.map((step) => {
    if (!OWN_RECIPE_KINDS.has(step.kind)) return step;
    const recipe = (recipes[step.kind] || []).find((r) => r.name === step.recipe);
    return recipe ? { ...step, ownRecipe: cloneRecipe(recipe) } : step;
  });
}

// Des étapes venues d'ailleurs (une brique, un préset) dont une recette du procédé porte un nom
// déjà pris ici par une autre définition : renommées, pour ne pas changer celle qui est déjà là.
function reconcileOwnRecipes(incoming) {
  const renamed = {};
  return incoming.map((step) => {
    if (!step.ownRecipe || !OWN_RECIPE_KINDS.has(step.kind)) return step;
    const key = `${step.kind}:${step.ownRecipe.name}`;
    if (renamed[key]) return { ...step, recipe: renamed[key].name, ownRecipe: cloneRecipe(renamed[key]) };
    const existing = ownRecipes(step.kind).get(step.ownRecipe.name);
    if (!existing || JSON.stringify(existing) === JSON.stringify(step.ownRecipe)) return step;
    const recipe = { ...cloneRecipe(step.ownRecipe), name: uniqueRecipeName(step.kind, step.ownRecipe.name) };
    renamed[key] = recipe;
    return { ...step, recipe: recipe.name, ownRecipe: cloneRecipe(recipe) };
  });
}
