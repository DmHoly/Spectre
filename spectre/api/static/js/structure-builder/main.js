/* Point d'entrée : charge les listes (matériaux, présets), puis bascule vers le bon mode
   (bibliothèque / évolution / modèle / structure choisie) selon ce que context.js a lu dans l'URL. */

async function loadPickers() {
  state.materials = await api.get(`/api/projects/${slug}/materials`);
  state.stepPresets = await api.get(`/api/projects/${slug}/presets-etapes`);
  document.getElementById("substrate-material").innerHTML = materialOptions("Si");
  renderKindFields(document.getElementById("kind-select").value);
}

async function init() {
  document.getElementById("crumb").textContent = "/ " + slug;
  if (evolveExperienceId) {
    document.getElementById("campaign-section").style.display = "none";
    document.getElementById("branch-choice-wrap").style.display = "block";
  }
  await loadPickers();
  renderSteps();
  renderObjectives();
  renderFrame();
  if (isLibraryMode) {
    await initLibraryMode();
  } else {
    await loadExistingProcess();
    await loadTemplateProcess();
    await loadChosenStructureForExperience();
  }
  addCampaignFactorRow();
}

init();
