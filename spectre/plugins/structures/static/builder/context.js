/* Constructeur de structure : lecture de l'URL (mode bibliothèque / expérience / évolution),
   état partagé entre tous les modules de ce dossier, et petits utilitaires de formulaire communs.
   Chargé en premier - tous les autres modules lisent `state` et utilisent `showError`/`clearError`. */

// Les routes du constructeur (spectre/plugins/structures/__init__.py) ; « nouvelle » tient lieu de l'id.
const libraryRoute = routeParams("/microprojets/{slug}/structures/bibliotheque/{structure_id}");
const brickRoute = routeParams("/microprojets/{slug}/briques-technologiques/bibliotheque/{brick_id}");
const evolveRoute = routeParams("/microprojets/{slug}/experiences/{experiment_id}/evoluer");
const { slug } = libraryRoute || brickRoute || evolveRoute || routeParams("/microprojets/{slug}/structures/nouvelle");
const isLibraryMode = Boolean(libraryRoute);
const libraryStructureId = isLibraryMode && libraryRoute.structure_id !== "nouvelle" ? libraryRoute.structure_id : null;
// Mode brique : réutilise ce même constructeur pour composer/éditer une brique technologique (une
// séquence d'étapes réutilisable, sans substrat propre - voir brick-mode.js). Mutuellement exclusif
// avec le mode bibliothèque, mêmes conventions d'URL (bibliotheque/{id|nouvelle}, ?dupliquer=1).
const isBrickMode = Boolean(brickRoute);
const brickId = isBrickMode && brickRoute.brick_id !== "nouvelle" ? brickRoute.brick_id : null;
const queryParams = new URLSearchParams(window.location.search);
const libraryDuplicateMode = queryParams.get("dupliquer") === "1";
const evolveExperienceId = evolveRoute ? evolveRoute.experiment_id : null;
// ?version= : partir d'une version passée de la piste (qui ne se continue que sur une nouvelle piste)
const evolveVersionId = evolveExperienceId ? queryParams.get("version") : null;
const templateExperienceId = !isLibraryMode && !isBrickMode && !evolveExperienceId ? queryParams.get("depuis") : null;
const chosenStructureId = !isLibraryMode && !isBrickMode && !evolveExperienceId ? queryParams.get("structure") : null;
// ?reference=<slug>&version=<1.1> : une nouvelle expérience partie d'une version de référence
// (references/static/start-picker.js) - la version demandée ; l'étude lancée ne retient
// (`reference_origin`) que celle que le constructeur a bien chargée (loadReferenceProcess) : une
// adresse vers une référence retirée ou inconnue ne laisse aucune fausse origine
const requestedReference =
  !isLibraryMode && !isBrickMode && !evolveExperienceId && queryParams.get("reference") && queryParams.get("version")
    ? { reference: queryParams.get("reference"), version: queryParams.get("version") }
    : null;
let referenceOrigin = null;
// ?plaque=W12-A3&plaque=…&depuis-mp=<slug>&depuis-etude=<piste>&depuis-version=<id> : une nouvelle
// expérience partie de plaques existantes (wafers/static/start-picker.js) - leurs lasermarks et
// l'étude qui les suit ; l'étude lancée ne retient (`wafer_origin`) que celle que le constructeur
// a bien chargée (loadWaferOrigin), ses plaques (`state.originWafers`) étant les seules suivies
const requestedWafers =
  !isLibraryMode && !isBrickMode && !evolveExperienceId && queryParams.getAll("plaque").length && queryParams.get("depuis-mp") && queryParams.get("depuis-etude")
    ? {
        lasermarks: queryParams.getAll("plaque"),
        microproject: queryParams.get("depuis-mp"),
        experimentId: queryParams.get("depuis-etude"),
        versionId: queryParams.get("depuis-version"),
      }
    : null;
let waferOrigin = null;
const returnTo = queryParams.get("retour"); // where "Enregistrer" in library/brick mode sends you back to

const state = {
  materials: [],
  recipes: { deposition: [], etch: [] },
  stepPresets: [], // à plat : intégrés, partagés et ceux du µprojet (champ scope)
  techBricks: [],
  steps: [],
  objectives: [],
  frames: null,
  materialColors: {},
  currentFrame: 0,
  campaignPlan: null,
  variationOverflow: 0, // plaques reprises en trop pour les variantes du plan (le lancement attend qu'on corrige)
  variationFactors: [], // [{step_id, field, field_label, values, scale}] - the DOE plan being built on écran 2
  variationEntities: [], // [{sample_id, location}] - one per row of the écran 3 table, positional
  originWafers: null, // partie de plaques existantes : leurs lasermarks, fixés (le tableau de l'écran 3 n'en change que l'emplacement et les FDL)
  wizardScreen: "structure", // écran courant de l'atelier : "structure", "intention" ou "variations" (ces deux derniers : mode expérience uniquement) - voir stages.js
  // Sélection dans le process flow (step-list.js) : -1 = le substrat, 0..n-1 = une étape. Pilote à
  // la fois l'inspecteur (inspector.js) et l'image affichée (simulation.js : la structure *après*
  // l'étape sélectionnée). Les modifications de l'inspecteur s'appliquent en direct à
  // state.steps[selectedIndex] - plus de mode "ajout" distinct d'un mode "modification".
  selectedIndex: -1,
  selectedStepIndices: new Set(), // sélection multiple (Ctrl/Maj+clic) - pour grouper en brique ou supprimer en bloc ; vidée à chaque changement structurel
  selectedBrickGroup: null, // brick_group_id dont l'inspecteur montre les actions (clic sur l'étiquette d'une brique)
  formDeclaredParams: [], // paramètres déclarés (voir form-widgets.js) du formulaire d'étape actuellement ouvert
  formLayerLabel: null, // étiquette de couche ({text, values}, voir layer-label.js) du formulaire d'étape ouvert
  formOwnRecipe: null, // recette du procédé (voir own-recipe.js) que nomme le formulaire d'étape ouvert, sinon null
  formOwnRecipeKind: null, // son type : "deposition" ou "etch"
  collapsedBrickGroups: new Set(), // brick_group_id des blocs repliés dans le flow (purement visuel)
  previewMode: "step", // "step" : dessin après l'étape sélectionnée ; "final" : toujours la structure finale
  frameLock: null, // image gardée à l'écran quand on sélectionne une étape en cliquant une couche du dessin (sinon la vue sauterait à cette étape)
  layerOrigins: null, // par image, l'étape d'origine de chaque couche - donnée par le serveur (step_index de chaque couche)
  derivedFrom: null, // library mode only: name of the structure this one was derived from, if any
  editingLibraryId: null, // library mode only: id of the saved structure being edited in place (null = new)
  editingBrickId: null, // brick mode only: id of the tech brick being edited in place (null = new)
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
