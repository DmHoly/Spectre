/* Client de l'API du plugin evidence : les preuves d'une expérience et leurs annotations. Comme les
   écritures d'experimentsApi, chacune envoie la version affichée (`versionId`, en-tête If-Match) :
   412 si la piste a avancé entre-temps, et rien n'est écrit. */

const evidenceApi = {
  add(microprojectSlug, experimentId, versionId, body) {
    return api.post(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(experimentId)}/preuves`, body, {
      ifMatch: versionId && `"${versionId}"`,
    });
  },
  updateAnnotations(microprojectSlug, experimentId, versionId, evidenceId, body) {
    return api.post(
      `/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(experimentId)}/preuves/${encodeURIComponent(evidenceId)}/annotations`,
      body,
      { ifMatch: versionId && `"${versionId}"` }
    );
  },
};
