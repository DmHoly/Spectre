/* Point d'entrée : charge les listes (matériaux, présets, briques), prépare l'atelier selon le mode
   (bibliothèque / brique / expérience - nouvelle, évolution, modèle, structure choisie, version de référence,
   plaques existantes) que
   context.js a lu dans l'URL, puis charge ce qui doit l'être. */

async function loadPickers() {
  [state.materials, state.recipes, state.stepPresets, state.techBricks] = await Promise.all([
    structuresApi.listMaterials(),
    structuresApi.listRecipes(),
    processLibraryApi.stepPresets({ microproject: slug }),
    processLibraryApi.techBricks({ microproject: slug }),
  ]);
  document.getElementById("substrate-material").innerHTML = materialOptions("Si");
  populateKindSelect();
  renderPaletteTools();
  renderBrickList();
}

function setupExperienceMode() {
  document.getElementById("experience-header").hidden = false;
  document.getElementById("stage-actions").hidden = false;
  setPageTitle("Nouvelle expérience");
  if (evolveExperienceId) {
    // Évolution / « partir d'une ref » : #launch-btn « Enregistrer cette évolution » enregistre
    // directement (entité + choix de piste sur l'écran intention). #continue-btn reste disponible
    // pour aller à l'écran variations faire varier un paramètre - c'est ce qui lance une campagne
    // rattachée à la version de départ (voir commitExperience / launch_campaign::from_ref).
    document.getElementById("entity-fields-wrap").hidden = false;
    document.getElementById("branch-choice-wrap").hidden = false;
    document.getElementById("launch-btn").hidden = false;
    const toIntention = document.getElementById("to-intention-btn");
    toIntention.classList.replace("btn-primary", "btn-line");
    const continueBtn = document.getElementById("continue-btn");
    continueBtn.textContent = "Faire varier (split) →";
    continueBtn.title = "Faire varier un paramètre : lance une campagne rattachée à cette version";
    continueBtn.classList.replace("btn-primary", "btn-line");
  }
}

async function init() {
  setPageTitle(isLibraryMode ? "Nouvelle structure" : isBrickMode ? "Nouvelle brique technologique" : "Nouvelle expérience");
  if (!isLibraryMode && !isBrickMode) setupExperienceMode();
  setStage("structure");
  try {
    await loadPickers();
  } catch (err) {
    showError(err);
    return;
  }
  renderObjectives();
  if (isLibraryMode) {
    await initLibraryMode();
  } else if (isBrickMode) {
    await initBrickMode();
  } else {
    if (pluginEnabled("intent_forms")) {
      intentFormSection = await mountIntentFormSection(document.getElementById("intent-form-box"), { microprojectSlug: slug, onError: showError });
    }
    await loadExistingProcess();
    await loadTemplateProcess();
    await loadReferenceProcess();
    await loadWaferOrigin();
    await loadChosenStructureForExperience();
  }
  // Tout ce qui est chargé programmatiquement (structure existante, modèle, brique...) constitue le
  // point de départ : l'historique d'annulation ne commence qu'à partir d'ici.
  renderSteps();
  resetHistory();
  // « Éditer la fiche » depuis l'en-tête d'une fiche : on arrive directement sur l'intention
  if (!isLibraryMode && !isBrickMode && queryParams.get("etape") === "intention") setStage("intention");
  const selectedChip = document.getElementById(`sb-chip-${state.selectedIndex}`);
  if (selectedChip) selectedChip.scrollIntoView({ block: "nearest", inline: "nearest" });
}

init();
