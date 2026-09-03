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
const librarySourceScope = queryParams.get("scope") || "projet";
const libraryDuplicateMode = queryParams.get("dupliquer") === "1";
const evolveExperienceId = !isLibraryMode && !isBrickMode && pathParts[2] === "experiences" ? pathParts[3] : null;
const templateExperienceId = !isLibraryMode && !isBrickMode && !evolveExperienceId ? queryParams.get("depuis") : null;
const chosenStructureName = !isLibraryMode && !isBrickMode && !evolveExperienceId ? queryParams.get("structure") : null;
const chosenStructureScope = queryParams.get("scope") || "projet";
const returnTo = queryParams.get("retour"); // where "Enregistrer" in library/brick mode sends you back to

const state = {
  materials: [],
  stepPresets: { presets: [], partagees: [], projet: [] },
  techBricks: { presets: [], partagees: [], projet: [] },
  steps: [],
  objectives: [],
  frames: null,
  materialColors: {},
  currentFrame: 0,
  campaignPlan: null,
  editingIndex: null,
  viewMode: "couches", // "couches" (click a layer, epitaxy-style) or "etapes" (full step list)
  showStepForm: false, // couches mode only: whether the add/edit form is open
  derivedFrom: null, // library mode only: name of the structure this one was derived from, if any
  editingLibraryName: null, // library mode only: name of the saved structure being edited in place (null = new)
  editingLibraryScope: null, // library mode only: "projet" or "partagee", matching editingLibraryName
  editingBrickName: null, // brick mode only: name of the tech brick being edited in place (null = new)
  editingBrickScope: null, // brick mode only: "projet" or "partagee", matching editingBrickName
  zoom: 1,
};

const errorBox = document.getElementById("error");
function showError(err) {
  errorBox.textContent = err.message || String(err);
  errorBox.style.display = "block";
}
function clearError() {
  errorBox.style.display = "none";
}

function lengthValue(id) {
  return { value: parseFloat(document.getElementById(id).value) || 0, unit: document.getElementById(id + "-unit").value };
}
