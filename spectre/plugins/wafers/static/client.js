/* Client de l'API du plugin wafers : les plaques (recherche, celles d'un µprojet), le passeport
   d'une plaque et les plaques d'une FDL. */

const wafersApi = {
  // filters : {q, fdl, microproject} - [{key, lasermark, count, microprojects, latest, fdl, locations}]
  list(filters) {
    return api.get(api.withQuery("/api/wafers", filters));
  },
  // waferKey : la clé d'une plaque, ou son lasermark tel qu'écrit
  get(waferKey) {
    return api.get(`/api/wafers/${encodeURIComponent(waferKey)}`);
  },
  // les plaques d'une FDL - {fdl, source, editable, known, wafers: [{lasermark, slot}]}
  fdl(fdl) {
    return api.get(`/api/fdls/${encodeURIComponent(fdl)}`);
  },
  // les plaques d'une FDL saisies à la main (base locale seulement) - lasermarks : dans l'ordre du lot
  setFdlWafers(fdl, lasermarks) {
    return api.put(`/api/fdls/${encodeURIComponent(fdl)}/wafers`, { lasermarks });
  },
};
