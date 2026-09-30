/* Constructeur de structure : lecture de l'URL (mode bibliothèque / expérience / évolution),
   état partagé entre tous les modules de ce dossier, et petits utilitaires de formulaire communs.
   Chargé en premier - tous les autres modules lisent `state` et utilisent `showError`/`clearError`. */

const pathParts = window.location.pathname.split("/").filter(Boolean);
const slug = pathParts[1];
const isLibraryMode = pathParts[2] === "structures" && pathParts[3] === "bibliotheque";
const libraryStructureName = isLibraryMode && pathParts[4] !== "nouvelle" ? decodeURIComponent(pathParts[4]) : null;
// Mode brique : réutilise ce même constructeur pour composer/éditer une brique technologique (une
// séquence d'étapes réutilisable, sans substrat propre - voir brick-mode.js). Mutuellement exclusif
// avec le mode bibliothèque, mêmes conventions d'URL (bibliotheque/{nom|nouvelle}, ?scope=/?dupliquer=1).
const isBrickMode = pathParts[2] === "briques-technologiques" && pathParts[3] === "bibliotheque";
const brickName = isBrickMode && pathParts[4] !== "nouvelle" ? decodeURIComponent(pathParts[4]) : null;
const queryParams = new URLSearchParams(window.location.search);
const librarySourceScope = queryParams.get("scope") || "microprojet";
const libraryDuplicateMode = queryParams.get("dupliquer") === "1";
const evolveExperienceId = !isLibraryMode && !isBrickMode && pathParts[2] === "experiences" ? pathParts[3] : null;
const templateExperienceId = !isLibraryMode && !isBrickMode && !evolveExperienceId ? queryParams.get("depuis") : null;
const chosenStructureName = !isLibraryMode && !isBrickMode && !evolveExperienceId ? queryParams.get("structure") : null;
const chosenStructureScope = queryParams.get("scope") || "microprojet";
const returnTo = queryParams.get("retour"); // where "Enregistrer" in library/brick mode sends you back to

const state = {
  materials: [],
  recipes: { deposition: [], etch: [] },
  stepPresets: { presets: [], partagees: [], projet: [] },
  techBricks: { presets: [], partagees: [], projet: [] },
  steps: [],
  objectives: [],
  frames: null,
  materialColors: {},
  currentFrame: 0,
  campaignPlan: null,
  variationFactors: [], // [{step_index, field, field_label, values}] - the DOE plan being built on écran 2
  variationEntities: [], // [{sample_id, location}] - one per row of the écran 3 table, positional
  wizardScreen: "structure", // écran courant de l'atelier : "structure", "intention" ou "variations" (ces deux derniers : mode expérience uniquement) - voir stages.js
  // Sélection dans le process flow (step-list.js) : -1 = le substrat, 0..n-1 = une étape. Pilote à
  // la fois l'inspecteur (inspector.js) et l'image affichée (simulation.js : la structure *après*
  // l'étape sélectionnée). Les modifications de l'inspecteur s'appliquent en direct à
  // state.steps[selectedIndex] - plus de mode "ajout" distinct d'un mode "modification".
  selectedIndex: -1,
  selectedStepIndices: new Set(), // sélection multiple (Ctrl/Maj+clic) - pour grouper en brique ou supprimer en bloc ; vidée à chaque changement structurel
  selectedBrickGroup: null, // brick_group_id dont l'inspecteur montre les actions (clic sur l'étiquette d'une brique)
  formDeclaredParams: [], // paramètres déclarés (voir form-widgets.js) du formulaire d'étape actuellement ouvert
  collapsedBrickGroups: new Set(), // brick_group_id des blocs repliés dans le flow (purement visuel)
  previewMode: "step", // "step" : dessin après l'étape sélectionnée ; "final" : toujours la structure finale
  frameLock: null, // image gardée à l'écran quand on sélectionne une étape en cliquant une couche du dessin (sinon la vue sauterait à cette étape)
  layerOrigins: null, // par image, l'étape d'origine de chaque couche (voir computeLayerOrigins, simulation.js)
  derivedFrom: null, // library mode only: name of the structure this one was derived from, if any
  editingLibraryName: null, // library mode only: name of the saved structure being edited in place (null = new)
  editingLibraryScope: null, // library mode only: "microprojet" or "partagee", matching editingLibraryName
  editingBrickName: null, // brick mode only: name of the tech brick being edited in place (null = new)
  editingBrickScope: null, // brick mode only: "microprojet" or "partagee", matching editingBrickName
  zoom: 1, // 1 = ajusté à la zone de dessin
};

const errorBox = document.getElementById("error");
function showError(err) {
  errorBox.textContent = err.message || String(err);
  errorBox.style.display = "block";
}
function clearError() {
  errorBox.style.display = "none";
}
errorBox.title = "Cliquer pour fermer";
errorBox.addEventListener("click", clearError);

// Libellé du bandeau (et de l'onglet) selon le mode - "Modifier la structure", "Enregistrer une
// évolution"... L'élément #page-title vit dans le bandeau de l'atelier.
function setPageTitle(text) {
  const el = document.getElementById("page-title");
  if (el) el.textContent = text;
  document.title = `${text} — Spectre`;
  const crumb = document.getElementById("crumb");
  if (crumb) {
    crumb.innerHTML = `/ <a href="/microprojets/${encodeURIComponent(slug)}">${escapeHtml(slug)}</a> / ${escapeHtml(text)}`;
  }
}

function lengthValue(id) {
  return { value: parseFloat(document.getElementById(id).value) || 0, unit: document.getElementById(id + "-unit").value };
}
