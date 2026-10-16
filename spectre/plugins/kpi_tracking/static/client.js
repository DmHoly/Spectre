/* Client de l'API du plugin kpi_tracking : les KPI qu'un projet corporate suit (choisis parmi les colonnes de
   KPI de PRISM) et leurs distributions sur les plaques de tous ses µprojets. */

const kpiTrackingApi = {
  // les KPI qu'on peut suivre -> [{key, hook, column, hook_title, unit, description}]
  catalog(areaSlug) {
    return api.get(`/api/areas/${encodeURIComponent(areaSlug)}/kpi-tracking/catalog`);
  },
  // les KPI suivis par le projet -> [{id, hook, column, label, title, filters, summary, goal, goal_summary, filter_columns, unit, description, hook_title, available}]
  list(areaSlug) {
    return api.get(`/api/areas/${encodeURIComponent(areaSlug)}/kpi-tracking/kpis`);
  },
  // suivre un KPI du catalogue : {hook, column, label?, filters?: [{column, op, value}], goal?: {mode, target?, min?, max?}} -> 201 ;
  // gérer le projet. goal.mode : max, min, target (avec target), range (avec min et max) - ce qui fait la meilleure plaque
  // op : gt, gte, lt, lte (valeur numérique), eq, ne, contains (texte), in (liste) ; une même colonne se suit
  // plusieurs fois avec des filtres différents (409 pour les mêmes)
  track(areaSlug, body) {
    return api.post(`/api/areas/${encodeURIComponent(areaSlug)}/kpi-tracking/kpis`, body);
  },
  // changer un KPI suivi : {label?} (vide : colonne et filtres), {filters?} (remplace les filtres, [] les retire)
  // et/ou {goal?} (remplace l'objectif, null le retire)
  update(areaSlug, kpiId, body) {
    return api.patch(`/api/areas/${encodeURIComponent(areaSlug)}/kpi-tracking/kpis/${encodeURIComponent(kpiId)}`, body);
  },
  untrack(areaSlug, kpiId) {
    return api.del(`/api/areas/${encodeURIComponent(areaSlug)}/kpi-tracking/kpis/${encodeURIComponent(kpiId)}`);
  },
  // les valeurs distinctes d'une colonne filtrable sur les plaques du projet (gérer le projet), pour un filtre à
  // choisir dans une liste : {kind: text|bool|number|empty, values: [{value, count}], distinct, minimum, maximum, wafers, source}
  values(areaSlug, hook, column) {
    return api.get(api.withQuery(`/api/areas/${encodeURIComponent(areaSlug)}/kpi-tracking/values`, { hook, column }));
  },
  // les boîtes à moustaches : {source, wafers, kpis: [{..., status, message, best (index de la meilleure plaque dans groups), groups: [{wafer, date, microprojects, studies, stats, outliers}]}]} ;
  // refresh : retaper la base de PRISM plutôt que lire son cache (gérer le projet)
  distributions(areaSlug, { refresh = false } = {}) {
    return api.get(api.withQuery(`/api/areas/${encodeURIComponent(areaSlug)}/kpi-tracking/distributions`, { refresh: refresh || undefined }));
  },
};
