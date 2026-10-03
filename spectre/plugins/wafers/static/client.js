/* Client de l'API du plugin wafers : les plaques (recherche, celles d'un µprojet) et le passeport
   d'une plaque. */

const wafersApi = {
  // filters : {q, fdl, microproject} - [{key, lasermark, count, microprojects, latest, fdl, locations}]
  list(filters) {
    return api.get(api.withQuery("/api/wafers", filters));
  },
  // waferKey : la clé d'une plaque, ou son lasermark tel qu'écrit
  get(waferKey) {
    return api.get(`/api/wafers/${encodeURIComponent(waferKey)}`);
  },
};
