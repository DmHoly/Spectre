/* Client de l'API du plugin kpis : les KPI d'un projet corporate et leurs séries mensuelles. */

const kpisApi = {
  list(areaSlug) {
    return api.get(`/api/management/${encodeURIComponent(areaSlug)}/tendances`);
  },
  series(areaSlug, kpiKey, months, variant) {
    return api.get(
      api.withQuery(`/api/management/${encodeURIComponent(areaSlug)}/tendances/${encodeURIComponent(kpiKey)}`, { mois: months, variante: variant })
    );
  },
};
