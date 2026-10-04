/* Client de l'API du plugin areas : projets corporate, leurs thématiques et leurs objectifs. */

const areasApi = {
  // tous les projets ; {team} : ceux d'une équipe. Chacun porte team, can_manage et can_delete
  list(params) {
    return api.get(api.withQuery("/api/areas", params));
  },
  // {name, description, strategy, code_prefix, team} : team obligatoire pour un manager (l'une des siennes)
  create(body) {
    return api.post("/api/areas", body);
  },
  get(areaSlug) {
    return api.get(`/api/areas/${encodeURIComponent(areaSlug)}`);
  },
  // {name, description, strategy, objectives_period, code_prefix} ; {team} (slug ou null) : admin seulement
  update(areaSlug, body) {
    return api.patch(`/api/areas/${encodeURIComponent(areaSlug)}`, body);
  },
  remove(areaSlug) {
    return api.del(`/api/areas/${encodeURIComponent(areaSlug)}`);
  },
  // toutes les thématiques, à plat ({id, slug, name, area}) ; celles d'un seul projet avec areaSlug
  listThematics(areaSlug) {
    return api.get(api.withQuery("/api/thematics", { area: areaSlug }));
  },
  createThematic(areaSlug, body) {
    return api.post(`/api/areas/${encodeURIComponent(areaSlug)}/thematics`, body);
  },
  getThematic(areaSlug, thematicSlug) {
    return api.get(`/api/areas/${encodeURIComponent(areaSlug)}/thematics/${encodeURIComponent(thematicSlug)}`);
  },
  updateThematic(areaSlug, thematicSlug, body) {
    return api.patch(`/api/areas/${encodeURIComponent(areaSlug)}/thematics/${encodeURIComponent(thematicSlug)}`, body);
  },
  removeThematic(areaSlug, thematicSlug) {
    return api.del(`/api/areas/${encodeURIComponent(areaSlug)}/thematics/${encodeURIComponent(thematicSlug)}`);
  },
  createObjective(areaSlug, body) {
    return api.post(`/api/areas/${encodeURIComponent(areaSlug)}/objectives`, body);
  },
  updateObjective(areaSlug, objectiveId, body) {
    return api.patch(`/api/areas/${encodeURIComponent(areaSlug)}/objectives/${encodeURIComponent(objectiveId)}`, body);
  },
  removeObjective(areaSlug, objectiveId) {
    return api.del(`/api/areas/${encodeURIComponent(areaSlug)}/objectives/${encodeURIComponent(objectiveId)}`);
  },
};
