/* Mode expérience : reprise d'un procédé existant (évolution d'une expérience, ou nouvelle
   expérience à partir d'un modèle), et lancement (création, évolution, ou campagne DOE).
   Une évolution peut s'enregistrer directement depuis l'écran structure ou intention
   (#launch-btn) ; un nouveau lancement passe par les trois écrans de l'atelier (structure ->
   intention -> variations -> #launch-btn-variations), tous deux aboutissant à commitExperience()
   ci-dessous - seule la provenance des `entities` diffère (les deux champs d'entité en évolution,
   le tableau de variations.js en nouveau lancement). */

// FDL de l'entité (écran intention, en évolution) - voir mountFdlField (wafers/static/fdl.js)
const entityFdlField = mountFdlField(document.getElementById("exp-entity-fdl"), { label: "FDL du wafer" });
document.querySelector("#exp-entity-fdl .fdl-field__input").id = "exp-entity-fdl-input";

// Formulaire d'intention du µprojet (intent_forms/static/intent-form-section.js), monté par main.js
let intentFormSection = null;
// La version de départ d'une évolution : sa version_id part en If-Match (continuer la piste) ou en
// from_version (une nouvelle piste, une campagne).
let evolveParent = null;

async function loadExistingProcess() {
  if (!evolveExperienceId) return;
  try {
    // Une expérience dont la structure n'est qu'une image (image-structure.html) n'a pas de procédé
    // à rouvrir : on la redessine à partir du seul substrat, le reste (intention, objectifs,
    // entité) est repris comme pour toute évolution.
    const data = await experimentsApi.process(slug, evolveExperienceId, evolveVersionId).catch((err) => {
      if (err.status === 404) return null;
      throw err;
    });
    if (data) {
      setSubstrateFields(data.substrate);
      // chaque étape garde son id : l'évolution (ou la fourche) le renvoie, l'étape reste la même
      state.steps = attachLayerLabels(attachDeclaredParams(data.steps, data.declared_params), data.layer_labels);
      selectLastStep();
      renderSteps();
    }
    setPageTitle(data ? "Éditer la fiche" : "Redessiner la structure");

    const detail = evolveVersionId
      ? await experimentsApi.getVersion(slug, evolveExperienceId, evolveVersionId)
      : await experimentsApi.get(slug, evolveExperienceId);
    evolveParent = detail;
    if (!detail.is_tip) {
      // une version passée ne se continue que sur une nouvelle piste
      document.getElementById("branch-fork").checked = true;
      document.getElementById("branch-continue").disabled = true;
      document.getElementById("new-branch-name").hidden = false;
    }
    document.getElementById("exp-title").value = detail.title;
    document.getElementById("exp-intent").value = detail.intent;
    document.getElementById("exp-hypothesis").value = detail.hypothesis || "";
    document.getElementById("exp-context").value = detail.context || "";
    const verification = detail.objective_verification || {};
    state.objectives = detail.objectives.map((o) => ({ ...o, verification_method: verification[o.name] || null }));
    renderObjectives();
    intentFormSection.fill(detail.form_answers);
    updateStageMeta();

    // en évolution, l'entité physique se transmet automatiquement de la version précédente
    // (voir experiments.py::evolve_experience) - le champ reste modifiable pour la corriger,
    // mais n'est obligatoire que si la piste n'en a jamais eu.
    const currentEntity = (detail.physical_tracking && detail.physical_tracking[0]) || {};
    document.getElementById("exp-entity-sample-id").value = currentEntity.sample_id || "";
    document.getElementById("exp-entity-location").value = currentEntity.location || "";
    entityFdlField.set(currentEntity.fdl || []);
    document.getElementById("entity-field-label").textContent = "Plaque suivie - lasermark";
    document.getElementById("entity-field-hint").textContent = currentEntity.sample_id
      ? "Reprise de la version précédente - modifiez-la si besoin."
      : "Aucune entité physique n'a encore été renseignée sur cette piste - il en faut une pour continuer.";
  } catch (err) {
    showError(err);
  }
}

// Titre/intention/objectifs/formulaire sont toujours lus depuis l'écran intention
// (#wizard-step-intention, masqué mais présent quand un autre écran est affiché) ; seules les
// `entities` varient selon l'appelant. `state.campaignPlan`
// (maintenu par variations.js) décide de l'endpoint exactement comme avant.
async function commitExperience(entities) {
  const title = document.getElementById("exp-title").value.trim();
  const intent = document.getElementById("exp-intent").value.trim();
  if (!title || !intent) {
    showError(new Error("Le titre et l'intention sont obligatoires."));
    setStage("intention");
    document.getElementById(title ? "exp-intent" : "exp-title").focus();
    return;
  }
  const structure = {
    kind: "process",
    substrate: substrateSpec(),
    steps: state.steps,
    declared_params: declaredParamsPayload(state.steps),
    layer_labels: layerLabelsPayload(state.steps),
  };
  const payload = {
    structure,
    title,
    intent,
    hypothesis: document.getElementById("exp-hypothesis").value || null,
    // le contexte tel qu'il est dans le champ : vidé, il est retiré de la fiche (voir structures.apply_context)
    context: document.getElementById("exp-context").value,
    objectives: state.objectives,
    entities,
    form_answers: intentFormSection ? intentFormSection.collect() : {},
  };
  if (evolveExperienceId && document.getElementById("branch-fork").checked) {
    const branchName = document.getElementById("new-branch-name").value.trim();
    if (!branchName) {
      showError(new Error("Donnez un nom à la nouvelle piste."));
      setStage("intention");
      document.getElementById("new-branch-name").focus();
      return;
    }
    payload.branch = branchName;
  }
  if (state.campaignPlan) {
    structure.kind = "campaign";
    structure.plan = state.campaignPlan;
  }
  // Une nouvelle piste partie de la version de départ (une fourche, ou une campagne) garde le lien
  // de filiation ; continuer la piste envoie la version affichée (If-Match).
  if (evolveExperienceId && (payload.branch || state.campaignPlan)) {
    payload.from_version = { experiment_id: evolveExperienceId, version_id: evolveParent ? evolveParent.version_id : null };
  }
  try {
    const result =
      evolveExperienceId && !payload.from_version
        ? await experimentsApi.evolve(slug, evolveExperienceId, evolveParent && evolveParent.version_id, payload)
        : await experimentsApi.create(slug, payload);
    window.location.href = `/microprojets/${encodeURIComponent(slug)}/experiences/${encodeURIComponent(result.id)}`;
  } catch (err) {
    const formMessage = intentFormSection && intentFormSection.errorMessage(err);
    showError(formMessage ? new Error(formMessage) : err);
  }
}

// Évolution directe (écran structure ou intention) - l'entité physique reste optionnelle ici
// (le serveur la reprend automatiquement de la version précédente, voir loadExistingProcess).
document.getElementById("launch-btn").addEventListener("click", () => {
  clearError();
  const entitySampleId = document.getElementById("exp-entity-sample-id").value.trim();
  const entityLocation = document.getElementById("exp-entity-location").value.trim();
  commitExperience(entitySampleId ? [{ sample_id: entitySampleId, location: entityLocation || null, fdl: entityFdlField.get() }] : []);
});

// Vers l'écran variations (bouton du bandeau ou étape 3 cliquée) : la structure et l'intention
// sont déjà en mémoire dans `state`, seule la validation minimale (titre/intention) garde le même
// garde-fou avant de basculer d'écran plutôt que de le reporter jusqu'au clic sur "Lancer".
function goToVariations() {
  clearError();
  const title = document.getElementById("exp-title").value.trim();
  const intent = document.getElementById("exp-intent").value.trim();
  if (!title || !intent) {
    showError(new Error("Le titre et l'intention sont obligatoires avant de définir les variations."));
    setStage("intention");
    document.getElementById(title ? "exp-intent" : "exp-title").focus();
    return;
  }
  showWizardStepVariations();
}

document.getElementById("continue-btn").addEventListener("click", goToVariations);

// Nouveau lancement, écran 3 : les entités viennent du tableau de variations plutôt que d'un
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
  document.getElementById("new-branch-name").hidden = true;
});
document.getElementById("branch-fork").addEventListener("change", () => {
  document.getElementById("new-branch-name").hidden = false;
  document.getElementById("new-branch-name").focus();
});

async function loadTemplateProcess() {
  if (!templateExperienceId) return;
  setPageTitle("Nouvelle expérience (structure reprise)");
  try {
    const data = await experimentsApi.process(slug, templateExperienceId);
    setSubstrateFields(data.substrate);
    // une nouvelle étude sans filiation : ses étapes sont neuves, le serveur leur donne leurs ids
    state.steps = attachLayerLabels(attachDeclaredParams(data.steps.map(withoutStepId), data.declared_params), data.layer_labels);
    selectLastStep();
    renderSteps();
  } catch (err) {
    showError(err);
  }
}
