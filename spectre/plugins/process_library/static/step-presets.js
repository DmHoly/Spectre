/* Page des présets d'étape : ceux qu'on peut insérer depuis ce µprojet (intégrés, partagés, du
   µprojet), regroupés par famille d'étape. Un préset se règle dans le constructeur, en mode préset
   (structures/static/builder/preset-mode.js) : « Nouveau » et « Modifier » y mènent, avec tous les
   formulaires d'étape (recette du procédé, paramètres déclarés, étiquette). */

const { slug } = routeParams("/microprojets/{slug}/presets-etapes");

// Les familles d'étape, dans l'ordre de la palette du constructeur (palette.js), et leur couleur.
const KINDS = {
  deposition: { label: "Dépôt", family: "Ajout de matière", color: "#1d6fae" },
  epitaxial_growth: { label: "Croissance épitaxiale", family: "Ajout de matière", color: "#2e8b57" },
  faceted_growth: { label: "Croissance facettée", family: "Ajout de matière", color: "#b8860b" },
  facet_envelope: { label: "Rattrapage des plans", family: "Ajout de matière", color: "#9a6b12" },
  lithography: { label: "Lithographie", family: "Motif & retrait", color: "#7a4a97" },
  etch: { label: "Gravure", family: "Motif & retrait", color: "#a45a3a" },
  resist_strip: { label: "Retrait de résine", family: "Motif & retrait", color: "#a45a3a" },
  planarization: { label: "Planarisation", family: "Motif & retrait", color: "#5c655e" },
  chemical: { label: "Étape chimique", family: "Étapes chimiques & autres", color: "#3f7d4a" },
  flip: { label: "Retournement", family: "Étapes chimiques & autres", color: "#6b5ca5" },
};
const FAMILIES = ["Ajout de matière", "Motif & retrait", "Étapes chimiques & autres"];
const NEW_KINDS = ["etch", "epitaxial_growth", "faceted_growth", "chemical", "deposition"];
const SCOPE_LABELS = { builtin: "intégré", shared: "partagé", microproject: "µprojet" };
const FIELD_LABELS = {
  thickness: "épaisseur",
  depth: "profondeur",
  rate_c: "vitesse C",
  rate_m: "vitesse M",
  rate_sp: "vitesse SP",
  rate_sp_inv: "vitesse SP inversée",
  semi_polar_angle_deg: "angle SP",
  angle_deg: "angle",
  material: "matériau",
  recipe: "recette",
  orientation: "orientation",
  target_level: "niveau cible",
  top_level: "niveau de troncature",
};

const state = { presets: [], canWrite: false, filter: "", scope: "" };

const errorBox = document.getElementById("error");
function showError(err) {
  errorBox.textContent = err.message || String(err);
  errorBox.style.display = "block";
  document.getElementById("flash").style.display = "none";
}
function showFlash(message) {
  const flashBox = document.getElementById("flash");
  flashBox.textContent = message;
  flashBox.style.display = "block";
  errorBox.style.display = "none";
}

function lengthText(length) {
  return length ? `${length.value} ${length.unit === "um" ? "µm" : length.unit === "A" ? "Å" : length.unit}` : "";
}

function stepSummary(preset) {
  const step = preset.step;
  const own = (preset.recipes && preset.recipes[step.kind]) || [];
  const recipe = step.recipe ? (own.some((r) => r.name === step.recipe) ? `${step.recipe} (recette propre)` : step.recipe) : "";
  switch (step.kind) {
    case "deposition":
      return [step.material, lengthText(step.thickness), recipe].filter(Boolean).join(" · ");
    case "etch": {
      const selective = own.find((r) => r.name === step.recipe);
      const targets = selective ? Object.keys(selective.selectivity_by_material || {}).concat(Object.keys(selective.selectivity_by_category || {})) : [];
      return [lengthText(step.depth), recipe, targets.length && selective.default_factor === 0 ? `ne grave que ${targets.join(", ")}` : ""].filter(Boolean).join(" · ");
    }
    case "faceted_growth":
      return `${step.material} · ${lengthText(step.thickness)} · C×${step.rate_c} M×${step.rate_m} SP×${step.rate_sp}${step.rate_sp_inv > 0 ? ` SP inv×${step.rate_sp_inv}` : ""} (${step.semi_polar_angle_deg}°)`;
    case "facet_envelope": {
      const planes = [step.c_plane !== false ? "C" : "", step.m_plane ? "M" : "", step.semi_polar_angle_deg != null ? `SP ${step.semi_polar_angle_deg}°` : ""].filter(Boolean);
      return [step.material, planes.join(" + "), step.top_level ? `tronqué à ${lengthText(step.top_level)}` : ""].filter(Boolean).join(" · ");
    }
    case "epitaxial_growth":
      return [step.material, lengthText(step.thickness), step.seed_materials && step.seed_materials.length ? `SAG sur ${step.seed_materials.join("/")}` : ""].filter(Boolean).join(" · ");
    case "lithography":
      return `${step.resist_material} · ${(step.openings || []).length} ouverture(s)`;
    case "planarization":
      return step.target_level ? `jusqu'à ${lengthText(step.target_level)}` : `jusqu'au ${step.stop_material}`;
    case "chemical":
      return step.description || "sans effet géométrique";
    case "resist_strip":
      return step.material;
    default:
      return "";
  }
}

function paramText(param) {
  const value = typeof param.value === "number" && (Math.abs(param.value) >= 1e5 || (param.value !== 0 && Math.abs(param.value) < 1e-3)) ? param.value.toExponential().replace("e+", "e") : param.value;
  return `${param.name} ${value}${param.unit ? ` ${param.unit}` : ""}`;
}

function variableLabel(field) {
  return field.startsWith("declared:") ? field.slice("declared:".length) : FIELD_LABELS[field] || field;
}

function editorHref(preset, { duplicate = false } = {}) {
  return `/microprojets/${encodeURIComponent(slug)}/presets-etapes/bibliotheque/${encodeURIComponent(preset.id)}${duplicate ? "?dupliquer=1" : ""}`;
}

function presetCard(preset) {
  const kind = KINDS[preset.step.kind] || { label: preset.step.kind, color: "var(--navy)" };
  const variable = new Set(preset.variable_fields || []);
  const params = (preset.declared_params || []).map(
    (p) => `<span class="sp-preset__param ${variable.has(`declared:${p.name}`) ? "is-variable" : ""}">${escapeHtml(paramText(p))}</span>`
  );
  const ownVariables = (preset.variable_fields || []).filter((f) => !f.startsWith("declared:")).map((f) => `<span class="sp-preset__param is-variable">${escapeHtml(variableLabel(f))}</span>`);
  const label = preset.layer_label ? `<span class="sp-preset__param" title="Affiché sur la structure">étiquette${preset.layer_label.text ? ` « ${escapeHtml(preset.layer_label.text)} »` : ""}</span>` : "";
  const actions = [];
  if (preset.can_edit) actions.push(`<a class="btn btn-line" href="${editorHref(preset)}">Modifier</a>`);
  if (state.canWrite) actions.push(`<a class="btn btn-line" href="${editorHref(preset, { duplicate: true })}">Dupliquer</a>`);
  if (preset.can_edit) actions.push(`<button class="btn btn-line js-remove" data-id="${escapeHtml(preset.id)}" type="button" style="color:var(--danger);">Supprimer</button>`);
  return `
    <article class="sp-preset" style="--kind:${kind.color};">
      <div class="sp-preset__top">
        <span class="sp-preset__name">${escapeHtml(preset.name)}</span>
        <span class="sp-preset__meta">${SCOPE_LABELS[preset.scope] || preset.scope} · v${preset.version || 1}</span>
      </div>
      <div class="sp-preset__kind">${escapeHtml(kind.label)}</div>
      <div class="sp-preset__summary">${escapeHtml(stepSummary(preset))}</div>
      ${params.length || ownVariables.length || label ? `<div class="sp-preset__params">${[...ownVariables, ...params, label].join("")}</div>` : ""}
      ${preset.notes ? `<div class="sp-preset__notes">${escapeHtml(preset.notes)}</div>` : ""}
      ${actions.length ? `<div class="sp-preset__actions">${actions.join("")}</div>` : ""}
    </article>`;
}

function matches(preset) {
  if (state.scope && preset.scope !== state.scope) return false;
  if (!state.filter) return true;
  const kind = KINDS[preset.step.kind];
  const haystack = [preset.name, preset.notes, kind && kind.label, stepSummary(preset), ...(preset.declared_params || []).map((p) => p.name)].join(" ").toLowerCase();
  return haystack.includes(state.filter);
}

function renderList() {
  const shown = state.presets.filter(matches);
  const list = document.getElementById("presets-list");
  if (!state.presets.length) {
    list.innerHTML = `<div class="help">Aucun préset pour l'instant.</div>`;
    return;
  }
  if (!shown.length) {
    list.innerHTML = `<div class="help">Aucun préset ne correspond.</div>`;
    return;
  }
  list.innerHTML =
    FAMILIES.map((family) => {
      const inFamily = shown.filter((p) => (KINDS[p.step.kind] || {}).family === family);
      if (!inFamily.length) return "";
      return `<section><h2 class="sp-presets__group-title">${escapeHtml(family)}</h2><div class="sp-presets__grid">${inFamily.map(presetCard).join("")}</div></section>`;
    }).join("") + `<div class="sp-presets__legend">En or : les paramètres que le préset propose de faire varier dans une campagne.</div>`;
}

document.getElementById("presets-list").addEventListener("click", async (event) => {
  const btn = event.target.closest(".js-remove");
  if (!btn) return;
  const preset = state.presets.find((p) => p.id === btn.dataset.id);
  if (!preset) return;
  const shared = preset.scope === "shared" ? " Il est partagé : il disparaîtra de tous les µprojets." : "";
  if (!window.confirm(`Supprimer le préset « ${preset.name} » ? Les structures déjà construites avec lui ne changent pas.${shared}`)) return;
  try {
    await processLibraryApi.deleteStepPreset(preset.id);
    await loadPresets();
    showFlash("Préset supprimé.");
  } catch (err) {
    showError(err);
  }
});

document.getElementById("preset-filter").addEventListener("input", (event) => {
  state.filter = event.target.value.trim().toLowerCase();
  renderList();
});
document.querySelector(".sp-presets__scopes").addEventListener("click", (event) => {
  const btn = event.target.closest("[data-scope]");
  if (!btn) return;
  state.scope = btn.dataset.scope;
  document.querySelectorAll(".sp-presets__scopes [data-scope]").forEach((b) => b.classList.toggle("is-active", b === btn));
  renderList();
});

async function loadPresets() {
  state.presets = await processLibraryApi.stepPresets({ microproject: slug });
  renderList();
}

async function init() {
  try {
    const microproject = await microprojectsApi.get(slug);
    state.canWrite = microproject.role === "editor" || microproject.role === "owner";
    document.getElementById("crumb").textContent = "/ " + microproject.name;
  } catch (err) {
    showError(err);
    return;
  }
  if (state.canWrite) {
    const shared = new URLSearchParams(window.location.search).get("partagee") === "1" ? "&partagee=1" : "";
    document.getElementById("new-preset-kinds").innerHTML = NEW_KINDS.map(
      (kind) => `<a class="btn btn-line" href="/microprojets/${encodeURIComponent(slug)}/presets-etapes/bibliotheque/nouvelle?type=${kind}${shared}">+ ${escapeHtml(KINDS[kind].label)}</a>`
    ).join("");
    document.getElementById("new-preset").hidden = false;
  }
  try {
    await loadPresets();
  } catch (err) {
    showError(err);
  }
}

init();
