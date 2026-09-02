/* Mode bibliothèque : choisir une structure enregistrée pour démarrer une expérience, et
   enregistrer/dupliquer une structure dans la bibliothèque (projet ou partagée). */

async function fetchSavedStructures() {
  return api.get(`/api/projects/${slug}/structures-sauvegardees`);
}

function findSavedStructure(list, name, scope) {
  const bucket = scope === "preset" ? list.presets : scope === "partagee" ? list.partagees : list.projet;
  return (bucket || []).find((s) => s.name === name) || null;
}

async function loadChosenStructureForExperience() {
  if (!chosenStructureName) return;
  try {
    const list = await fetchSavedStructures();
    const found = findSavedStructure(list, chosenStructureName, chosenStructureScope);
    if (!found) {
      showError(new Error(`Structure "${chosenStructureName}" introuvable dans la bibliothèque.`));
      return;
    }
    setSubstrateFields(found.substrate);
    state.steps = found.steps;
    renderSteps();
    document.getElementById("based-on-note").style.display = "";
    document.getElementById("based-on-name").textContent = found.name;
    document.getElementById("edit-structure-link").href =
      `/projets/${slug}/structures/bibliotheque/${encodeURIComponent(found.name)}` +
      `?scope=${chosenStructureScope}&dupliquer=1&retour=nouvelle-experience`;
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
    return;
  }
  const partagee = document.getElementById("library-shared-checkbox").checked;
  const payload = {
    name,
    substrate: substrateSpec(),
    steps: state.steps,
    derived_from: state.derivedFrom || null,
    partagee,
  };
  try {
    if (!forceNew && state.editingLibraryName) {
      await api.put(
        `/api/projects/${slug}/structures-sauvegardees/${encodeURIComponent(state.editingLibraryName)}` +
          `?partagee=${state.editingLibraryScope === "partagee"}`,
        payload
      );
    } else {
      await api.post(`/api/projects/${slug}/structures-sauvegardees`, payload);
    }
    const scope = partagee ? "partagee" : "projet";
    if (returnTo === "nouvelle-experience") {
      window.location.href = `/projets/${slug}/structures/nouvelle?structure=${encodeURIComponent(name)}&scope=${scope}`;
    } else {
      window.location.href = `/projets/${slug}#structures`;
    }
  } catch (err) {
    showError(err);
  }
}

async function initLibraryMode() {
  document.getElementById("library-header").style.display = "";
  document.getElementById("experience-sections").style.display = "none";

  if (!libraryStructureName) {
    document.getElementById("page-title").textContent = "Nouvelle structure";
    return;
  }
  try {
    const list = await fetchSavedStructures();
    const found = findSavedStructure(list, libraryStructureName, librarySourceScope);
    if (!found) {
      showError(new Error(`Structure "${libraryStructureName}" introuvable.`));
      return;
    }
    setSubstrateFields(found.substrate);
    state.steps = found.steps;
    renderSteps();
    // A preset (structureforge built-in) has no backing store to edit in place - forcing
    // duplicate mode turns "Modifier" into "dupliquer sous un nouveau nom", which is the only
    // thing that makes sense for it.
    const duplicateMode = libraryDuplicateMode || librarySourceScope === "preset";
    if (duplicateMode) {
      document.getElementById("page-title").textContent =
        librarySourceScope === "preset" ? "Enregistrer ce préset sous un nouveau nom" : "Dupliquer une structure";
      document.getElementById("library-name").placeholder = `ex : ${found.name} + ...`;
      state.derivedFrom = found.name;
      document.getElementById("library-derived-note").style.display = "";
      document.getElementById("library-derived-note").textContent = `Dérivée de : ${found.name}`;
    } else {
      document.getElementById("page-title").textContent = "Modifier la structure";
      document.getElementById("library-name").value = found.name;
      document.getElementById("library-shared-checkbox").checked = librarySourceScope === "partagee";
      state.derivedFrom = found.derived_from || null;
      state.editingLibraryName = found.name;
      state.editingLibraryScope = librarySourceScope;
      document.getElementById("library-save-as-btn").style.display = "";
      if (found.derived_from) {
        document.getElementById("library-derived-note").style.display = "";
        document.getElementById("library-derived-note").textContent = `Dérivée de : ${found.derived_from}`;
      }
    }
  } catch (err) {
    showError(err);
  }
}
