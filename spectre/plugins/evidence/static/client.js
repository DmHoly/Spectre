/* Client de l'API du plugin evidence : les preuves d'une expérience et leurs annotations. */

const evidenceApi = {
  add(microprojectSlug, ref, body) {
    return api.post(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(ref)}/preuves`, body);
  },
  updateAnnotations(microprojectSlug, ref, evidenceId, body) {
    return api.post(
      `/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(ref)}/preuves/${encodeURIComponent(evidenceId)}/annotations`,
      body
    );
  },
};
