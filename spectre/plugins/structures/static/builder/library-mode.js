/* Mode bibliothèque : choisir une structure enregistrée pour démarrer une expérience, et
   enregistrer/dupliquer une structure dans la bibliothèque (projet ou partagée). */

async function loadChosenStructureForExperience() {
  if (!chosenStructureId) return;
  try {
    const found = await processLibraryApi.savedStructure(chosenStructureId);
    setSubstrateFields(found.substrate);
    state.steps = attachBricks(attachLayerLabels(attachDeclaredParams(found.steps, found.declared_params), found.layer_labels), found.bricks);
    selectLastStep();
    renderSteps();
    document.getElementById("based-on-note").hidden = false;
    document.getElementById("based-on-name").textContent = found.name;
    document.getElementById("edit-structure-link").href =
      `/microprojets/${slug}/structures/bibliotheque/${encodeURIComponent(found.id)}?dupliquer=1&retour=nouvelle-experience`;
  } catch (err) {
    showError(err);
  }
}

document.getElementById("library-save-btn").addEventListener("click", () => saveLibraryStructure(false));
document.getElementById("library-save-as-btn").addEventListener("click", () => saveLibraryStructure(true));

async function saveLibraryStructure(forceNew) {
  clearError();
  const name = document.getElementById("library-name").value.trim();
  if (!name) {
    showError(new Error("Donnez un nom à cette structure pour l'enregistrer."));
    document.getElementById("library-name").focus();
    return;
  }
  const payload = {
    name,
    substrate: substrateSpec(),
    steps: state.steps,
    declared_params: declaredParamsPayload(state.steps),
    layer_labels: layerLabelsPayload(state.steps),
    bricks: bricksPayload(state.steps),
    scope: document.getElementById("library-shared-checkbox").checked ? "shared" : "microproject",
    microproject: slug,
  };
  try {
    const saved =
      !forceNew && state.editingLibraryId
        ? await processLibraryApi.updateSavedStructure(state.editingLibraryId, payload)
        : await processLibraryApi.createSavedStructure({ ...payload, derived_from: state.derivedFrom || null });
    if (returnTo === "nouvelle-experience") {
      window.location.href = `/microprojets/${slug}/structures/nouvelle?structure=${encodeURIComponent(saved.id)}`;
    } else if (returnTo === "bibliotheque") {
      window.location.href = "/bibliotheque";
    } else {
      window.location.href = `/microprojets/${slug}#structures`;
    }
  } catch (err) {
    showError(err);
  }
}

async function initLibraryMode() {
  document.getElementById("library-header").hidden = false;
  document.getElementById("library-save-btn").hidden = false;
  // Arrivée depuis le hub /bibliotheque (?partagee=1) : la structure sera par défaut "partagée
  // avec tous les µprojets", pas propre au µprojet de travail choisi pour ouvrir l'éditeur.
  if (queryParams.get("partagee") === "1") document.getElementById("library-shared-checkbox").checked = true;

  if (!libraryStructureId) {
    setPageTitle("Nouvelle structure");
    document.getElementById("library-name").focus();
    return;
  }
  try {
    const found = await processLibraryApi.savedStructure(libraryStructureId);
    setSubstrateFields(found.substrate);
    state.steps = attachBricks(attachLayerLabels(attachDeclaredParams(found.steps, found.declared_params), found.layer_labels), found.bricks);
    selectLastStep();
    renderSteps();
    // A built-in structure (or one we may not change) has nothing to edit in place - forcing
    // duplicate mode turns "Modifier" into "dupliquer sous un nouveau nom", which is the only
    // thing that makes sense for it.
    const duplicateMode = libraryDuplicateMode || !found.can_edit;
    if (duplicateMode) {
      setPageTitle(found.scope === "builtin" ? "Enregistrer cette structure intégrée sous un nouveau nom" : "Dupliquer une structure");
      document.getElementById("library-name").placeholder = `ex : ${found.name} + ...`;
      state.derivedFrom = found.name;
      document.getElementById("library-derived-note").hidden = false;
      document.getElementById("library-derived-note").textContent = `Dérivée de : ${found.name}`;
    } else {
      setPageTitle("Modifier la structure");
      document.getElementById("library-name").value = found.name;
      document.getElementById("library-shared-checkbox").checked = found.scope === "shared";
      state.derivedFrom = found.derived_from || null;
      state.editingLibraryId = found.id;
      document.getElementById("library-save-as-btn").hidden = false;
      if (found.derived_from) {
        document.getElementById("library-derived-note").hidden = false;
        // le nom d'une structure enregistrée, ou la version d'une étude publiée depuis « Évolution des structures »
        const origin = found.derived_from;
        const label = typeof origin === "string" ? origin : `${origin.ref || origin.experiment_id} (µprojet ${origin.microproject})`;
        document.getElementById("library-derived-note").textContent = `Dérivée de : ${label}`;
      }
    }
  } catch (err) {
    showError(err);
  }
}
