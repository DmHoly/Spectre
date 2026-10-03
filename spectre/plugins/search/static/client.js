/* Client de l'API du plugin search : la recherche de la barre du haut. */

const searchApi = {
  // [{type, label, detail, badge, url}] ; types : "wafer,fdl"... (tous par défaut)
  search(query, types) {
    return api.get(api.withQuery("/api/search", { q: query, types }));
  },
};
