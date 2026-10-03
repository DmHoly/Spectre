/* Client de l'API du plugin lots : lots de fabrication, leurs wafers et leurs thématiques visées.
   `code` : le code d'un lot. */

const lotsApi = {
  // filter : actifs | sortis | annules | tous
  list(filter) {
    return api.get(api.withQuery("/api/lots", { statut: filter }));
  },
  create(body) {
    return api.post("/api/lots", body);
  },
  search(query) {
    return api.get(api.withQuery("/api/lots/recherche", { q: query }));
  },
  // les lots où l'on peut ajouter des wafers (sélecteur « Ajouter au lot »)
  selection() {
    return api.get("/api/lots/selection");
  },
  thematicOptions() {
    return api.get("/api/lots/thematiques");
  },
  get(code) {
    return api.get(`/api/lots/${encodeURIComponent(code)}`);
  },
  update(code, body) {
    return api.put(`/api/lots/${encodeURIComponent(code)}`, body);
  },
  remove(code) {
    return api.del(`/api/lots/${encodeURIComponent(code)}`);
  },
  addWafers(code, body) {
    return api.post(`/api/lots/${encodeURIComponent(code)}/wafers`, body);
  },
  removeWafer(code, lasermark) {
    return api.del(`/api/lots/${encodeURIComponent(code)}/wafers/${encodeURIComponent(lasermark)}`);
  },
  setThematics(code, body) {
    return api.put(`/api/lots/${encodeURIComponent(code)}/thematiques`, body);
  },
};
