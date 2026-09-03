/* Mode brique : composer/éditer une brique technologique (une séquence d'étapes réutilisable, sans
   substrat propre) - même mécanique que le mode bibliothèque (library-mode.js) mais contre
   /briques-technologiques. Le substrat affiché dans le constructeur ne sert qu'à prévisualiser les
   étapes pendant la composition ; il n'est jamais envoyé à l'API ni enregistré avec la brique. */

async function fetchTechBricks() {
  return api.get(`/api/projects/${slug}/briques-technologiques`);
}

function findTechBrick(list, name, scope) {
  const bucket = scope === "preset" ? list.presets : scope === "partagee" ? list.partagees : list.projet;
  return (bucket || []).find((b) => b.name === name) || null;
}

document.getElementById("brick-save-btn").addEventListener("click", () => saveTechBrick(false));
document.getElementById("brick-save-as-btn").addEventListener("click", () => saveTechBrick(true));

async function saveTechBrick(forceNew) {
  clearError();
  const name = document.getElementById("brick-name").value.trim();
  if (!name) {
    showError(new Error("Donnez un nom à cette brique pour l'enregistrer."));
    return;
  }
  if (state.steps.length === 0) {
    showError(new Error("Ajoutez au moins une étape avant d'enregistrer la brique."));
    return;
  }
  const partagee = document.getElementById("brick-shared-checkbox").checked;
  const payload = { name, steps: state.steps, notes: document.getElementById("brick-notes").value.trim() || null, partagee };
  try {
    if (!forceNew && state.editingBrickName) {
      await api.put(
        `/api/projects/${slug}/briques-technologiques/${encodeURIComponent(state.editingBrickName)}` +
          `?partagee=${state.editingBrickScope === "partagee"}`,
        payload
      );
    } else {
      await api.post(`/api/projects/${slug}/briques-technologiques`, payload);
    }
    window.location.href = `/projets/${slug}/briques-technologiques`;
  } catch (err) {
    showError(err);
  }
}

async function initBrickMode() {
  document.getElementById("brick-header").style.display = "";
  document.getElementById("experience-sections").style.display = "none";
  document.getElementById("brick-preview-note").style.display = "";

  if (!brickName) {
    document.getElementById("page-title").textContent = "Nouvelle brique technologique";
    return;
  }
  try {
    const list = await fetchTechBricks();
    // les paramètres ?scope=/?dupliquer=1 sont génériques (voir context.js) - réutilisés tels
    // quels ici, comme en mode bibliothèque.
    const found = findTechBrick(list, brickName, librarySourceScope);
    if (!found) {
      showError(new Error(`Brique "${brickName}" introuvable.`));
      return;
    }
    state.steps = found.steps;
    renderSteps();
    // Un préset (aucun aujourd'hui, mais même garde-fou que la bibliothèque de structures/présets
    // d'étape) n'a pas de support à éditer en place.
    const duplicateMode = libraryDuplicateMode || librarySourceScope === "preset";
    if (duplicateMode) {
      document.getElementById("page-title").textContent =
        librarySourceScope === "preset" ? "Enregistrer cette brique sous un nouveau nom" : "Dupliquer une brique";
      document.getElementById("brick-name").placeholder = `ex : ${found.name} + ...`;
    } else {
      document.getElementById("page-title").textContent = "Modifier la brique";
      document.getElementById("brick-name").value = found.name;
      document.getElementById("brick-shared-checkbox").checked = librarySourceScope === "partagee";
      document.getElementById("brick-notes").value = found.notes || "";
      state.editingBrickName = found.name;
      state.editingBrickScope = librarySourceScope;
      document.getElementById("brick-save-as-btn").style.display = "";
    }
  } catch (err) {
    showError(err);
  }
}
