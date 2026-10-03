/* Client de l'API du plugin kpis : les KPI d'un projet corporate et leurs séries mensuelles. */

const kpisApi = {
  list(areaSlug) {
    return api.get(`/api/areas/${encodeURIComponent(areaSlug)}/kpis`);
  },
  series(areaSlug, kpiKey, months, variant) {
    return api.get(api.withQuery(`/api/areas/${encodeURIComponent(areaSlug)}/kpis/${encodeURIComponent(kpiKey)}`, { months, variant }));
  },
};
