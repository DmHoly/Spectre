/* Client de l'API du plugin characterization : catalogue des types de données (PRISM, ou démo),
   fiche d'un type et requête. Les graphiques documentaires d'une fiche portent leur `url`. */

const characterizationApi = {
  // filters : {category, status: "implemented" | "planned", by_wafer: true | false}
  list(filters) {
    return api.get(api.withQuery("/api/characterization/data-types", filters));
  },
  categories() {
    return api.get("/api/characterization/categories");
  },
  get(dataTypeKey) {
    return api.get(`/api/characterization/data-types/${encodeURIComponent(dataTypeKey)}`);
  },
  // body : {parameters: {wafer_names: [...]}, refresh}
  query(dataTypeKey, body) {
    return api.post(`/api/characterization/data-types/${encodeURIComponent(dataTypeKey)}/queries`, body);
  },
};
