/* Mode expérience : reprise d'un procédé existant (évolution d'une expérience, ou nouvelle
   expérience à partir d'un modèle), et lancement (création, évolution, ou campagne DOE). */

async function loadExistingProcess() {
  if (!evolveExperienceId) return;
  try {
    const data = await api.get(`/api/projects/${slug}/experiences/${evolveExperienceId}/process`);
    setSubstrateFields(data.substrate);
    state.steps = data.steps;
    renderSteps();
    document.getElementById("page-title").textContent = "Enregistrer une évolution";
    document.getElementById("launch-btn").textContent = "Enregistrer cette évolution";

    const detail = await api.get(`/api/projects/${slug}/experiences/${evolveExperienceId}`);
    document.getElementById("exp-title").value = detail.title;
    document.getElementById("exp-intent").value = detail.intent;
    document.getElementById("exp-hypothesis").value = detail.hypothesis || "";
    const verification = detail.objective_verification || {};
    state.objectives = detail.objectives.map((o) => ({ ...o, verification_method: verification[o.name] || null }));
    renderObjectives();
  } catch (err) {
    showError(err);
  }
}

document.getElementById("launch-btn").addEventListener("click", async () => {
  clearError();
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
      endpoint = `/api/projects/${slug}/experiences/campagne`;
    } else if (evolveExperienceId) {
      endpoint = `/api/projects/${slug}/experiences/${evolveExperienceId}/evoluer`;
    } else {
      endpoint = `/api/projects/${slug}/experiences`;
    }
    const result = await api.post(endpoint, payload);
    window.location.href = `/projets/${slug}/experiences/${result.id}`;
  } catch (err) {
    showError(err);
  }
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
    const data = await api.get(`/api/projects/${slug}/experiences/${templateExperienceId}/process`);
    setSubstrateFields(data.substrate);
    state.steps = data.steps;
    renderSteps();
  } catch (err) {
    showError(err);
  }
}
