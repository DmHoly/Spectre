/* Client de l'API du plugin simulation_progress : l'avancement d'une simulation du constructeur. */

const simulationProgressApi = {
  // runId : l'identifiant donné à la simulation (structuresApi.simulate(body, runId)) ->
  // {state: "running" | "done" | "failed", total, done, resumed, step: {index, name} | null, elapsed}
  // - 404 tant qu'elle n'est pas partie, ou une fois son suivi oublié
  get(runId) {
    return api.get(`/api/simulation-runs/${encodeURIComponent(runId)}`);
  },
};
