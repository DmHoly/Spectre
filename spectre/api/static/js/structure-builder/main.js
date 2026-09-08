/* Point d'entrée : charge les listes (matériaux, présets), puis bascule vers le bon mode
   (bibliothèque / évolution / modèle / structure choisie) selon ce que context.js a lu dans l'URL. */

async function loadPickers() {
  state.materials = await api.get(`/api/microprojets/${slug}/materials`);
  state.recipes = await api.get(`/api/microprojets/${slug}/recettes`);
  state.stepPresets = await api.get(`/api/microprojets/${slug}/presets-etapes`);
  state.techBricks = await api.get(`/api/microprojets/${slug}/briques-technologiques`);
  document.getElementById("substrate-material").innerHTML = materialOptions("Si");
  renderKindFields(document.getElementById("kind-select").value);
  populateInsertBrickSelect();
}

async function init() {
  document.getElementById("crumb").textContent = "/ " + slug;
  if (evolveExperienceId) {
    // Évolution / « partir d'une ref » : le chemin rapide reste un seul écran (#launch-btn
    // « Enregistrer cette évolution », entité + choix de piste sur l'écran 1). Mais #continue-btn
    // reste visible aussi : il mène à l'écran 2 pour cliquer une étape et faire varier un paramètre
    // - c'est ce qui lance une campagne rattachée à la version de départ (voir commitExperience /
    // launch_campaign::from_ref).
    document.getElementById("entity-fields-wrap").style.display = "";
    document.getElementById("branch-choice-wrap").style.display = "block";
    document.getElementById("launch-btn").style.display = "";
    const continueBtn = document.getElementById("continue-btn");
    continueBtn.textContent = "Faire varier un paramètre (split) →";
    continueBtn.classList.remove("btn-primary");
    continueBtn.classList.add("btn-line");
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
  // Tout ce qui est chargé programmatiquement (structure existante, modèle, brique...) constitue le
  // point de départ : l'historique d'annulation ne commence qu'à partir d'ici.
  resetHistory();
}

init();
