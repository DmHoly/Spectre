/* Client de l'API du plugin meta_analysis : les analyses de plaques - une plaque de référence et celles qu'on lui
   compare, la question posée et la conclusion. Une analyse se rend sous la forme {id, title, question, conclusion,
   reference: {key, lasermark}, wafers: [{key, lasermark}] (la référence d'abord), created_by, updated_by, updated_at}. */

const metaAnalysisApi = {
  // filters : {wafer} - seulement les analyses où paraît cette plaque ; la plus récemment modifiée d'abord
  list(filters) {
    return api.get(api.withQuery("/api/analyses", filters || {}));
  },
  get(analysisId) {
    return api.get(`/api/analyses/${encodeURIComponent(analysisId)}`);
  },
  // body : {title, question, wafers: [lasermark]} - la première plaque est la référence
  create(body) {
    return api.post("/api/analyses", body);
  },
  // body : les champs à changer parmi {title, question, conclusion, wafers} ; wafers remplace toutes les plaques
  update(analysisId, body) {
    return api.patch(`/api/analyses/${encodeURIComponent(analysisId)}`, body);
  },
  remove(analysisId) {
    return api.del(`/api/analyses/${encodeURIComponent(analysisId)}`);
  },
};
