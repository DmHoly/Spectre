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
  // les plaques à ajouter, cherchées comme dans la barre du haut (lasermark, run, lot, µprojet, FDL) - {groups:
  // [{kind: wafer|run|lot|name|microproject|fdl, label, detail, total, wafers: [{key, lasermark, detail}]}]}
  searchWafers(q) {
    return api.get(api.withQuery("/api/analyses/wafer-search", { q }));
  },
  // body : {title, question, wafers: [lasermark]} - la première plaque est la référence
  create(body) {
    return api.post("/api/analyses", body);
  },
  // body : les champs à changer parmi {title, question, conclusion, wafers, kpis} ; wafers remplace toutes les plaques,
  // kpis tous les KPI comparés ([{hook, column, label, filters, better}])
  update(analysisId, body) {
    return api.patch(`/api/analyses/${encodeURIComponent(analysisId)}`, body);
  },
  // pour chaque KPI comparé, une boîte par plaque et l'écart de sa médiane à la référence - {source, kpis: [{hook, column,
  // title, unit, hook_title, better, status, message, groups: [{key, wafer, date, dates, stats, outliers, delta}]}]}
  kpis(analysisId, { refresh = false } = {}) {
    return api.get(api.withQuery(`/api/analyses/${encodeURIComponent(analysisId)}/kpis`, { refresh: refresh || undefined }));
  },
  // ce qu'on peut comparer : {catalog: [{key, hook, column, hook_title, unit, ...}], suggested: [{hook, column, label,
  // filters, better, title, area}]} - les KPI suivis par les projets des plaques d'abord
  kpiChoices(analysisId) {
    return api.get(`/api/analyses/${encodeURIComponent(analysisId)}/kpi-choices`);
  },
  remove(analysisId) {
    return api.del(`/api/analyses/${encodeURIComponent(analysisId)}`);
  },
};
