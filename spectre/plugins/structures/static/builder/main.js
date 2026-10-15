/* Point d'entrée : charge les listes (matériaux, présets, briques), prépare l'atelier selon le mode
   (bibliothèque / brique / expérience - nouvelle, évolution, modèle, structure choisie, version de référence,
   plaques existantes) que
   context.js a lu dans l'URL, puis charge ce qui doit l'être. */

async function loadPickers() {
  // les références (leur dernière version, proposée comme brique) : un renseignement, la page s'en passe
  const references = pluginEnabled("references") && typeof referencesApi !== "undefined" ? referencesApi.list().catch(() => []) : Promise.resolve([]);
  [state.materials, state.recipes, state.stepPresets, state.techBricks, state.savedStructures, state.references] = await Promise.all([
    structuresApi.listMaterials(),
    structuresApi.listRecipes(),
    processLibraryApi.stepPresets({ microproject: slug }),
    processLibraryApi.techBricks({ microproject: slug }),
    processLibraryApi.savedStructures({ microproject: slug }).catch(() => []),
    references,
  ]);
  document.getElementById("substrate-material").innerHTML = materialOptions("Si");
  populateKindSelect();
  renderPaletteTools();
  renderBrickList();
  renderPresetList();
}

function setupExperienceMode() {
  document.getElementById("experience-header").hidden = false;
  document.getElementById("stage-actions").hidden = false;
  setPageTitle("Nouvelle expérience");
  if (evolveExperienceId && !planId) {
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
  if (evolveVariant !== null) {
    // la correction d'une seule variante : l'écran structure seulement, « Enregistrer la correction »
    document.querySelectorAll(".sb-stage").forEach((btn) => {
      if (btn.dataset.stage !== "structure") btn.hidden = true;
    });
    document.getElementById("to-intention-btn").hidden = true;
    document.getElementById("launch-btn").textContent = "Enregistrer la correction";
    document.getElementById("launch-btn").title = "La structure corrigée remplace le dessin automatique de cette variante (une retouche : pas de nouveau numéro de version)";
  }
}

async function init() {
  setPageTitle(isLibraryMode ? "Nouvelle structure" : isBrickMode ? "Nouvelle brique technologique" : isPresetMode ? "Nouveau préset d'étape" : "Nouvelle expérience");
  if (!isLibraryMode && !isBrickMode && !isPresetMode) setupExperienceMode();
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
  } else if (isPresetMode) {
    await initPresetMode();
  } else {
    if (pluginEnabled("intent_forms")) {
      intentFormSection = await mountIntentFormSection(document.getElementById("intent-form-box"), { microprojectSlug: slug, onError: showError });
    }
    await loadExistingProcess();
    await loadTemplateProcess();
    await loadReferenceProcess();
    await loadWaferOrigin();
    await loadStartPlace();
    await loadComposition();
    await loadChosenStructureForExperience();
    await loadPlan();
  }
  // Tout ce qui est chargé programmatiquement (structure existante, modèle, brique...) constitue le
  // point de départ : l'historique d'annulation ne commence qu'à partir d'ici.
  renderSteps();
  prefetchReferenceBricks(); // palette.js : les versions de référence copiées dans la structure chargée
  resetHistory();
  // « Éditer la fiche » depuis l'en-tête d'une fiche : on arrive directement sur l'intention
  if (!isLibraryMode && !isBrickMode && !isPresetMode && queryParams.get("etape") === "intention") setStage("intention");
  const selectedChip = document.getElementById(`sb-chip-${state.selectedIndex}`);
  if (selectedChip) selectedChip.scrollIntoView({ block: "nearest", inline: "nearest" });
}

init();
