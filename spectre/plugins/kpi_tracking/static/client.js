/* Client de l'API du plugin kpi_tracking : les KPI qu'un µprojet suit (choisis parmi les colonnes de KPI
   de PRISM) et leurs distributions sur les plaques que ses études suivent. */

const kpiTrackingApi = {
  // les KPI qu'on peut suivre -> [{key, hook, column, hook_title, unit, description}]
  catalog(slug) {
    return api.get(`/api/microprojects/${encodeURIComponent(slug)}/kpi-tracking/catalog`);
  },
  // les KPI suivis par le µprojet -> [{id, hook, column, label, title, unit, description, hook_title, available}]
  list(slug) {
    return api.get(`/api/microprojects/${encodeURIComponent(slug)}/kpi-tracking/kpis`);
  },
  // suivre un KPI du catalogue : {hook, column, label?} -> 201 (409 s'il est déjà suivi)
  track(slug, body) {
    return api.post(`/api/microprojects/${encodeURIComponent(slug)}/kpi-tracking/kpis`, body);
  },
  // renommer l'affichage d'un KPI suivi : {label} (vide : la colonne PRISM)
  rename(slug, kpiId, label) {
    return api.patch(`/api/microprojects/${encodeURIComponent(slug)}/kpi-tracking/kpis/${encodeURIComponent(kpiId)}`, { label });
  },
  untrack(slug, kpiId) {
    return api.del(`/api/microprojects/${encodeURIComponent(slug)}/kpi-tracking/kpis/${encodeURIComponent(kpiId)}`);
  },
  // les boîtes à moustaches : {source, wafers, kpis: [{..., status, message, groups: [{wafer, studies, stats, outliers}]}]} ;
  // refresh : retaper la base de PRISM plutôt que lire son cache (rôle editor)
  distributions(slug, { refresh = false } = {}) {
    return api.get(api.withQuery(`/api/microprojects/${encodeURIComponent(slug)}/kpi-tracking/distributions`, { refresh: refresh || undefined }));
  },
};
