/* Mode brique : composer/éditer une brique technologique (une séquence d'étapes réutilisable) -
   même mécanique que le mode bibliothèque (library-mode.js) mais contre les briques technologiques.
   Le substrat affiché dans le constructeur ne sert qu'à prévisualiser les étapes pendant la
   composition, sauf pour une **brique de départ** (case « Brique de départ ») : son substrat, avec
   son réseau de fils, est enregistré avec elle, et une structure vide où on la pose le reprend. */

function syncBrickStartNote() {
  const starting = document.getElementById("brick-start-checkbox").checked;
  document.getElementById("brick-preview-note").textContent = starting
    ? "Brique de départ : ce substrat et son réseau de fils sont enregistrés avec la brique - posée dans une structure vide, elle les apporte ; ailleurs, seules ses étapes s'appliquent."
    : "Ce substrat ne sert qu'à prévisualiser les étapes - il n'est pas enregistré avec la brique, qui s'appliquera sur la structure existante au moment de l'insertion (cochez « Brique de départ » pour le garder).";
}
document.getElementById("brick-start-checkbox").addEventListener("change", syncBrickStartNote);

document.getElementById("brick-save-btn").addEventListener("click", () => saveTechBrick(false));
document.getElementById("brick-save-as-btn").addEventListener("click", () => saveTechBrick(true));

async function saveTechBrick(forceNew) {
  clearError();
  const name = document.getElementById("brick-name").value.trim();
  if (!name) {
    showError(new Error("Donnez un nom à cette brique pour l'enregistrer."));
    document.getElementById("brick-name").focus();
    return;
  }
  const length = Array.from(name).length;
  if (length > BRICK_NAME_MAX) {
    // une brique enregistrée avant la limite : la raccourcir pour l'enregistrer
    showError(new Error(`Le nom d'une brique fait au plus ${BRICK_NAME_MAX} caractères (celui-ci en a ${length}).`));
    document.getElementById("brick-name").focus();
    return;
  }
  const steps = state.steps;
  if (steps.length === 0) {
    showError(new Error("Ajoutez au moins une étape avant d'enregistrer la brique."));
    return;
  }
  const payload = {
    name,
    steps,
    declared_params: declaredParamsPayload(steps),
    layer_labels: layerLabelsPayload(steps),
    recipes: processRecipesPayload(steps),
    preset_origins: presetOriginsPayload(steps),
    lattice_openings: latticeOpeningsPayload(steps),
    bricks: bricksPayload(steps),
    substrate: document.getElementById("brick-start-checkbox").checked ? substrateSpec() : null,
    notes: document.getElementById("brick-notes").value.trim() || null,
    scope: document.getElementById("brick-shared-checkbox").checked ? "shared" : "microproject",
    microproject: slug,
  };
  try {
    if (!forceNew && state.editingBrickId) {
      await processLibraryApi.updateTechBrick(state.editingBrickId, payload);
    } else {
      await processLibraryApi.createTechBrick(payload);
    }
    window.location.href = returnTo === "bibliotheque" ? "/bibliotheque" : `/microprojets/${slug}/briques-technologiques`;
  } catch (err) {
    showError(err);
  }
}

async function initBrickMode() {
  document.getElementById("brick-header").hidden = false;
  document.getElementById("brick-save-btn").hidden = false;
  document.getElementById("brick-preview-note").hidden = false;
  syncBrickStartNote();
  // Arrivée depuis le hub /bibliotheque (?partagee=1) : brique partagée par défaut.
  if (queryParams.get("partagee") === "1") document.getElementById("brick-shared-checkbox").checked = true;

  if (!brickId) {
    setPageTitle("Nouvelle brique technologique");
    document.getElementById("brick-name").focus();
    return;
  }
  try {
    // le paramètre ?dupliquer=1 est générique (voir context.js) - réutilisé tel quel ici, comme
    // en mode bibliothèque.
    const found = await processLibraryApi.techBrick(brickId);
    state.steps = attachStepExtras(found.steps, found);
    if (found.substrate) {
      setSubstrateFields(found.substrate);
      document.getElementById("brick-start-checkbox").checked = true;
      syncBrickStartNote();
    }
    selectLastStep();
    renderSteps();
    // Une brique intégrée (ou qu'on ne peut pas modifier) n'a rien à éditer en place.
    const duplicateMode = libraryDuplicateMode || !found.can_edit;
    if (duplicateMode) {
      setPageTitle(found.scope === "builtin" ? "Enregistrer cette brique sous un nouveau nom" : "Dupliquer une brique");
      document.getElementById("brick-name").placeholder = `ex : ${found.name} + ...`;
    } else {
      setPageTitle("Modifier la brique");
      document.getElementById("brick-name").value = found.name;
      document.getElementById("brick-shared-checkbox").checked = found.scope === "shared";
      document.getElementById("brick-notes").value = found.notes || "";
      state.editingBrickId = found.id;
      document.getElementById("brick-save-as-btn").hidden = false;
    }
  } catch (err) {
    showError(err);
  }
}
