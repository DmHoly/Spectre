/* Mode expérience : reprise d'un procédé existant (évolution d'une expérience, ou nouvelle
   expérience à partir d'un modèle), et lancement (création, évolution, ou campagne DOE).
   Une évolution reste un seul écran (#launch-btn, comme avant) ; un nouveau lancement passe par
   les deux écrans du magicien (#continue-btn -> écran variations -> #launch-btn-variations), tous
   deux aboutissant à commitExperience() ci-dessous - seule la provenance des `entities` diffère
   (les deux champs d'entité en évolution, le tableau de variations.js en nouveau lancement). */

async function loadExistingProcess() {
  if (!evolveExperienceId) return;
  try {
    const data = await api.get(`/api/microprojets/${slug}/experiences/${evolveExperienceId}/process`);
    setSubstrateFields(data.substrate);
    state.steps = data.steps;
    renderSteps();
    document.getElementById("page-title").textContent = "Enregistrer une évolution";
    document.getElementById("launch-btn").textContent = "Enregistrer cette évolution";

    const detail = await api.get(`/api/microprojets/${slug}/experiences/${evolveExperienceId}`);
    document.getElementById("exp-title").value = detail.title;
    document.getElementById("exp-intent").value = detail.intent;
    document.getElementById("exp-hypothesis").value = detail.hypothesis || "";
    const verification = detail.objective_verification || {};
    state.objectives = detail.objectives.map((o) => ({ ...o, verification_method: verification[o.name] || null }));
    renderObjectives();
    fillIntentFormAnswers(detail.form_answers);

    // en évolution, l'entité physique se transmet automatiquement de la version précédente
    // (voir experiments.py::evolve_experience) - le champ reste modifiable pour la corriger,
    // mais n'est obligatoire que si la piste n'en a jamais eu.
    const currentEntity = (detail.physical_tracking && detail.physical_tracking[0]) || {};
    document.getElementById("exp-entity-sample-id").value = currentEntity.sample_id || "";
    document.getElementById("exp-entity-location").value = currentEntity.location || "";
    document.getElementById("entity-field-label").textContent = "Entité physique";
    document.getElementById("entity-field-hint").textContent = currentEntity.sample_id
      ? "Reprise de la version précédente - modifiez-la si besoin."
      : "Aucune entité physique n'a encore été renseignée sur cette piste - il en faut une pour continuer.";
  } catch (err) {
    showError(err);
  }
}

// Titre/intention/objectifs/formulaire sont toujours lus depuis l'écran 1 (#wizard-step-intention,
// jamais quitté en évolution) ; seules les `entities` varient selon l'appelant. `state.campaignPlan`
// (maintenu par variations.js) décide de l'endpoint exactement comme avant.
async function commitExperience(entities) {
  const title = document.getElementById("exp-title").value.trim();
  const intent = document.getElementById("exp-intent").value.trim();
  if (!title || !intent) {
    showError(new Error("Le titre et l'intention sont obligatoires."));
    return;
  }
  const payload = {
    substrate: substrateSpec(),
    steps: state.steps,
    title,
    intent,
    hypothesis: document.getElementById("exp-hypothesis").value || null,
    objectives: state.objectives,
    entities,
    form_answers: collectIntentFormAnswers(),
  };
  if (evolveExperienceId && document.getElementById("branch-fork").checked) {
    const branchName = document.getElementById("new-branch-name").value.trim();
    if (!branchName) {
      showError(new Error("Donnez un nom à la nouvelle piste."));
      return;
    }
    payload.new_branch = branchName;
  }
  try {
    let endpoint;
    if (state.campaignPlan) {
      payload.plan = state.campaignPlan;
      // Campagne partie d'une ref / d'une expérience : on garde le lien de filiation (voir
      // launch_campaign::from_ref) - `payload.new_branch` est déjà posé plus haut si "fork".
      if (evolveExperienceId) payload.from_ref = evolveExperienceId;
      endpoint = `/api/microprojets/${slug}/experiences/campagne`;
    } else if (evolveExperienceId) {
      endpoint = `/api/microprojets/${slug}/experiences/${evolveExperienceId}/evoluer`;
    } else {
      endpoint = `/api/microprojets/${slug}/experiences`;
    }
    const result = await api.post(endpoint, payload);
    window.location.href = `/microprojets/${slug}/experiences/${result.id}`;
  } catch (err) {
    const formMessage = intentFormErrorMessage(err);
    showError(formMessage ? new Error(formMessage) : err);
  }
}

// Évolution : un seul écran, comportement inchangé - l'entité physique reste optionnelle ici
// (le serveur la reprend automatiquement de la version précédente, voir loadExistingProcess).
document.getElementById("launch-btn").addEventListener("click", () => {
  clearError();
  const entitySampleId = document.getElementById("exp-entity-sample-id").value.trim();
  const entityLocation = document.getElementById("exp-entity-location").value.trim();
  commitExperience(entitySampleId ? [{ sample_id: entitySampleId, location: entityLocation || null }] : []);
});

// Nouveau lancement, écran 1 -> écran 2 : la structure et l'intention sont déjà en mémoire dans
// `state`, seule la validation minimale (titre/intention) garde le même garde-fou qu'avant de
// basculer d'écran plutôt que de le reporter jusqu'au clic sur "Lancer".
document.getElementById("continue-btn").addEventListener("click", () => {
  clearError();
  const title = document.getElementById("exp-title").value.trim();
  const intent = document.getElementById("exp-intent").value.trim();
  if (!title || !intent) {
    showError(new Error("Le titre et l'intention sont obligatoires."));
    return;
  }
  showWizardStepVariations();
});

// Nouveau lancement, écran 2 : les entités viennent du tableau de variations plutôt que d'un
// unique champ - au moins un échantillon doit être nommé pour lancer le suivi (même garde-fou
// qu'avant, appliqué à la colonne "Nom du wafer" du tableau plutôt qu'à un champ unique).
document.getElementById("launch-btn-variations").addEventListener("click", () => {
  clearError();
  const tableEntities = variationTableEntities();
  // Une évolution simple (sans variation) peut laisser le tableau vide - le serveur reprend
  // l'entité de la version précédente. On envoie alors une liste vide plutôt qu'une ligne blanche,
  // qui écraserait l'entité héritée (voir evolve_experience). Un nouveau lancement / une campagne
  // exigent au moins un échantillon nommé (positions gardées pour l'alignement des variantes).
  const evolveNoSplit = evolveExperienceId && !state.campaignPlan;
  if (evolveNoSplit) {
    commitExperience(tableEntities.filter((e) => e.sample_id));
    return;
  }
  if (!tableEntities.some((e) => e.sample_id)) {
    showError(new Error("L'entité physique (l'échantillon réel suivi) est obligatoire - nommez au moins un wafer dans le tableau."));
    return;
  }
  commitExperience(tableEntities);
});

document.getElementById("branch-continue").addEventListener("change", () => {
  document.getElementById("new-branch-name").style.display = "none";
});
document.getElementById("branch-fork").addEventListener("change", () => {
  document.getElementById("new-branch-name").style.display = "";
});

async function loadTemplateProcess() {
  if (!templateExperienceId) return;
  document.getElementById("page-title").textContent = "Nouvelle expérience (structure reprise)";
  try {
    const data = await api.get(`/api/microprojets/${slug}/experiences/${templateExperienceId}/process`);
    setSubstrateFields(data.substrate);
    state.steps = data.steps;
    renderSteps();
  } catch (err) {
    showError(err);
  }
}
