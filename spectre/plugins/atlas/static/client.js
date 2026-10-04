/* Client de l'API du plugin atlas : la vue graphe d'un projet corporate. */

const atlasApi = {
  get(areaSlug) {
    return api.get(`/api/areas/${encodeURIComponent(areaSlug)}/atlas`);
  },
};
