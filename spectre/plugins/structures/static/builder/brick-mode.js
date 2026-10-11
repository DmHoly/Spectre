/* Mode brique : composer/éditer une brique technologique (une séquence d'étapes réutilisable, sans
   substrat propre) - même mécanique que le mode bibliothèque (library-mode.js) mais contre
   les briques technologiques. Le substrat affiché dans le constructeur ne sert qu'à prévisualiser les
   étapes pendant la composition ; il n'est jamais envoyé à l'API ni enregistré avec la brique.

   Une macro-étape (rôle, assembly.js) : un gabarit SAG garde son substrat et son réseau ; une épi ou
   un procédé se compose sur les macro-étapes d'avant (posées depuis l'assemblage), qui ne servent
   qu'à l'aperçu - elles ne sont pas enregistrées avec la brique, seulement leurs ids (`preview_on`),
   pour les reposer à la réouverture. La recette d'épi ne contient ainsi pas le SAG. */

// Les étapes de la brique : sans celles des macro-étapes d'un autre rôle (son contexte d'aperçu).
function brickOwnSteps(role) {
  return state.steps.filter((step) => !step.brick_role || step.brick_role === role);
}

function brickContextSources(role) {
  const ids = [];
  state.steps.forEach((step) => {
    if (step.brick_role && step.brick_role !== role && step.brick_source && !ids.includes(step.brick_source)) ids.push(step.brick_source);
  });
  return ids.slice(0, 3);
}

function syncBrickRoleNote() {
  const role = document.getElementById("brick-role").value;
  const note = document.getElementById("brick-preview-note");
  note.textContent =
    role === "sag"
      ? "Gabarit SAG : ce substrat et son réseau de fils sont enregistrés avec la brique - le départ de toute structure bâtie dessus."
      : role
        ? "Ce substrat ne sert qu'à l'aperçu. Posez le gabarit SAG (et l'épi, pour un procédé) depuis l'assemblage : ils ne servent qu'à l'aperçu et ne sont pas enregistrés avec la brique."
        : "Ce substrat ne sert qu'à prévisualiser les étapes - il n'est pas enregistré avec la brique, qui s'appliquera sur la structure existante au moment de l'insertion.";
}
document.getElementById("brick-role").addEventListener("change", syncBrickRoleNote);

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
  const role = document.getElementById("brick-role").value || null;
  // la brique elle-même, sans son contexte d'aperçu ni l'étiquette de son propre rôle (elle le porte)
  const steps = brickOwnSteps(role).map((step) => (step.brick_role === role ? stripBrickTag(step) : step));
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
    role,
    substrate: role === "sag" ? substrateSpec() : null,
    preview_on: role && role !== "sag" ? brickContextSources(role) : [],
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
    window.location.href =
      returnTo === "bibliotheque" ? "/bibliotheque" : returnTo === "macro-etapes" || role ? `/microprojets/${slug}/macro-etapes` : `/microprojets/${slug}/briques-technologiques`;
  } catch (err) {
    showError(err);
  }
}

async function initBrickMode() {
  document.getElementById("brick-header").hidden = false;
  document.getElementById("brick-save-btn").hidden = false;
  document.getElementById("brick-preview-note").hidden = false;
  syncBrickRoleNote();
  // Arrivée depuis le hub /bibliotheque (?partagee=1) : brique partagée par défaut.
  if (queryParams.get("partagee") === "1") document.getElementById("brick-shared-checkbox").checked = true;

  if (!brickId) {
    // ?role=sag|epi|process : une nouvelle macro-étape (page des macro-étapes, « + Nouveau »)
    const role = queryParams.get("role");
    if (BRICK_ROLE_ORDER.includes(role)) {
      document.getElementById("brick-role").value = role;
      syncBrickRoleNote();
      setPageTitle(`Nouvelle macro-étape · ${brickRoleLabel(role)}`);
      document.getElementById("brick-name").focus();
      return;
    }
    setPageTitle("Nouvelle brique technologique");
    document.getElementById("brick-name").focus();
    return;
  }
  try {
    // le paramètre ?dupliquer=1 est générique (voir context.js) - réutilisé tel quel ici, comme
    // en mode bibliothèque.
    const found = await processLibraryApi.techBrick(brickId);
    state.steps = attachStepExtras(found.steps, found);
    document.getElementById("brick-role").value = found.role || "";
    syncBrickRoleNote();
    if (found.role === "sag" && found.substrate) setSubstrateFields(found.substrate);
    // une épi, un procédé : reposés sur les macro-étapes d'avant (l'aperçu), dans l'ordre de l'assemblage
    if (found.role && found.role !== "sag") {
      (found.preview_on || [])
        .map(findBrickEntry)
        .filter((b) => b && b.role && b.role !== found.role)
        .sort((a, b) => BRICK_ROLE_ORDER.indexOf(a.role) - BRICK_ROLE_ORDER.indexOf(b.role))
        .forEach((b) => assembleBrick(b.role, b));
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
