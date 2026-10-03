/* Client de l'API du plugin kpis_demo : la fiche (fictive) d'une étude derrière un point de tendance. */

const kpisDemoApi = {
  study(areaSlug, kpiKey, studyId) {
    return api.get(
      `/api/management/${encodeURIComponent(areaSlug)}/tendances/${encodeURIComponent(kpiKey)}/etudes/${encodeURIComponent(studyId)}`
    );
  },
};
