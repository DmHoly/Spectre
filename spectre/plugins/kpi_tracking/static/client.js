/* Client de l'API du plugin kpi_tracking : les KPI qu'un projet corporate suit (choisis parmi les colonnes de
   KPI de PRISM) et leurs distributions sur les plaques de tous ses µprojets. */

const kpiTrackingApi = {
  // les KPI qu'on peut suivre -> [{key, hook, column, hook_title, unit, description}]
  catalog(areaSlug) {
    return api.get(`/api/areas/${encodeURIComponent(areaSlug)}/kpi-tracking/catalog`);
  },
  // les KPI suivis par le projet -> [{id, hook, column, label, title, unit, description, hook_title, available}]
  list(areaSlug) {
    return api.get(`/api/areas/${encodeURIComponent(areaSlug)}/kpi-tracking/kpis`);
  },
  // suivre un KPI du catalogue : {hook, column, label?} -> 201 (409 s'il est déjà suivi) ; gérer le projet
  track(areaSlug, body) {
    return api.post(`/api/areas/${encodeURIComponent(areaSlug)}/kpi-tracking/kpis`, body);
  },
  // renommer l'affichage d'un KPI suivi : {label} (vide : la colonne PRISM)
  rename(areaSlug, kpiId, label) {
    return api.patch(`/api/areas/${encodeURIComponent(areaSlug)}/kpi-tracking/kpis/${encodeURIComponent(kpiId)}`, { label });
  },
  untrack(areaSlug, kpiId) {
    return api.del(`/api/areas/${encodeURIComponent(areaSlug)}/kpi-tracking/kpis/${encodeURIComponent(kpiId)}`);
  },
  // les boîtes à moustaches : {source, wafers, kpis: [{..., status, message, groups: [{wafer, microprojects, studies, stats, outliers}]}]} ;
  // refresh : retaper la base de PRISM plutôt que lire son cache (gérer le projet)
  distributions(areaSlug, { refresh = false } = {}) {
    return api.get(api.withQuery(`/api/areas/${encodeURIComponent(areaSlug)}/kpi-tracking/distributions`, { refresh: refresh || undefined }));
  },
};
