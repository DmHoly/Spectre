/* Point d'entrée : charge les listes (matériaux, présets), puis bascule vers le bon mode
   (bibliothèque / évolution / modèle / structure choisie) selon ce que context.js a lu dans l'URL. */

async function loadPickers() {
  state.materials = await api.get(`/api/projects/${slug}/materials`);
  state.recipes = await api.get(`/api/projects/${slug}/recettes`);
  state.stepPresets = await api.get(`/api/projects/${slug}/presets-etapes`);
  state.techBricks = await api.get(`/api/projects/${slug}/briques-technologiques`);
  document.getElementById("substrate-material").innerHTML = materialOptions("Si");
  renderKindFields(document.getElementById("kind-select").value);
  populateInsertBrickSelect();
}

async function init() {
  document.getElementById("crumb").textContent = "/ " + slug;
  if (evolveExperienceId) {
    // Une évolution reste un seul écran : l'entité physique (optionnelle ici, voir
    // loadExistingProcess) et le choix de piste réapparaissent, "Continuer" cède la place à
    // "Enregistrer cette évolution" - jamais d'écran 2 (une évolution ne lance jamais de campagne).
    document.getElementById("entity-fields-wrap").style.display = "";
    document.getElementById("branch-choice-wrap").style.display = "block";
    document.getElementById("continue-btn").style.display = "none";
    document.getElementById("launch-btn").style.display = "";
  }
  await loadPickers();
  renderSteps();
  renderObjectives();
  renderFrame();
  if (isLibraryMode) {
    await initLibraryMode();
  } else if (isBrickMode) {
    await initBrickMode();
  } else {
    await loadIntentForm();
    await loadExistingProcess();
    await loadTemplateProcess();
    await loadChosenStructureForExperience();
  }
}

init();
