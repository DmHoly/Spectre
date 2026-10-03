/* Client de l'API du plugin wafers : recherche d'une plaque, son passeport, et l'historique des
   entités (lasermarks, emplacements, FDL) d'un µprojet. */

const wafersApi = {
  search(query) {
    return api.get(api.withQuery("/api/plaques/recherche", { q: query }));
  },
  get(lasermark) {
    return api.get(`/api/plaques/${encodeURIComponent(lasermark)}`);
  },
  entityHistory(microprojectSlug) {
    return api.get(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/entites/historique`);
  },
};
