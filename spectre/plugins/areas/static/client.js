/* Client de l'API du plugin areas : projets corporate, leurs thématiques et leurs objectifs. */

const areasApi = {
  list() {
    return api.get("/api/management");
  },
  create(body) {
    return api.post("/api/management", body);
  },
  get(areaSlug) {
    return api.get(`/api/management/${encodeURIComponent(areaSlug)}`);
  },
  update(areaSlug, body) {
    return api.put(`/api/management/${encodeURIComponent(areaSlug)}`, body);
  },
  remove(areaSlug) {
    return api.del(`/api/management/${encodeURIComponent(areaSlug)}`);
  },
  assignMicroproject(areaSlug, body) {
    return api.post(`/api/management/${encodeURIComponent(areaSlug)}/microprojets`, body);
  },
  createThematic(areaSlug, body) {
    return api.post(`/api/management/${encodeURIComponent(areaSlug)}/thematiques`, body);
  },
  getThematic(areaSlug, thematicSlug) {
    return api.get(`/api/management/${encodeURIComponent(areaSlug)}/thematiques/${encodeURIComponent(thematicSlug)}`);
  },
  updateThematic(areaSlug, thematicSlug, body) {
    return api.put(`/api/management/${encodeURIComponent(areaSlug)}/thematiques/${encodeURIComponent(thematicSlug)}`, body);
  },
  removeThematic(areaSlug, thematicSlug) {
    return api.del(`/api/management/${encodeURIComponent(areaSlug)}/thematiques/${encodeURIComponent(thematicSlug)}`);
  },
  createObjective(areaSlug, body) {
    return api.post(`/api/management/${encodeURIComponent(areaSlug)}/objectifs`, body);
  },
  updateObjective(areaSlug, objectiveId, body) {
    return api.put(`/api/management/${encodeURIComponent(areaSlug)}/objectifs/${encodeURIComponent(objectiveId)}`, body);
  },
  removeObjective(areaSlug, objectiveId) {
    return api.del(`/api/management/${encodeURIComponent(areaSlug)}/objectifs/${encodeURIComponent(objectiveId)}`);
  },
};
