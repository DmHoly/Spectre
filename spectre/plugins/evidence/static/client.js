/* Client de l'API du plugin evidence : les preuves d'une expérience et leurs annotations. Comme les
   écritures d'experimentsApi, chacune envoie la version affichée (`versionId`, en-tête If-Match) :
   412 si la piste a avancé entre-temps, et rien n'est écrit. */

const evidenceApi = {
  // les preuves de la version `version` (la pointe sans) : [{id, description, source, metrics,
  // step_index, kind, objective, interpretation, graph_config, annotations, links, images: [{id, url, caption, ...}]}]
  list(microprojectSlug, experimentId, version) {
    return api.get(
      api.withQuery(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/experiments/${encodeURIComponent(experimentId)}/evidence`, {
        version,
      })
    );
  },
  // body : {description, source, links, images: [{image_id, caption}], metric_name, metric_value,
  // step_index, objective, interpretation} - les images sont téléversées d'abord (attachmentsApi.upload)
  add(microprojectSlug, experimentId, versionId, body) {
    return api.post(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/experiments/${encodeURIComponent(experimentId)}/evidence`, body, {
      ifMatch: versionId && `"${versionId}"`,
    });
  },
  replaceAnnotations(microprojectSlug, experimentId, versionId, evidenceId, body) {
    return api.put(
      `/api/microprojects/${encodeURIComponent(microprojectSlug)}/experiments/${encodeURIComponent(experimentId)}/evidence/${encodeURIComponent(evidenceId)}/annotations`,
      body,
      { ifMatch: versionId && `"${versionId}"` }
    );
  },
};
