/* Client de l'API du plugin characterization : catalogue des types de données (hooks PRISM),
   exécution d'une requête et URL des graphiques documentaires. */

const characterizationApi = {
  hooks() {
    return api.get("/api/donnees/hooks");
  },
  categories() {
    return api.get("/api/donnees/categories");
  },
  hook(key) {
    return api.get(`/api/donnees/hooks/${encodeURIComponent(key)}`);
  },
  run(key, body) {
    return api.post(`/api/donnees/hooks/${encodeURIComponent(key)}/executer`, body);
  },
  chartUrl(key, chartKey) {
    return `/api/donnees/hooks/${encodeURIComponent(key)}/graphiques/${encodeURIComponent(chartKey)}`;
  },
};
