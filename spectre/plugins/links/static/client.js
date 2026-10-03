/* Client de l'API du plugin links : liens entre µprojets et entre entités physiques.
   `filters` : { microproject, area } (slugs) - les liens qui touchent ce µprojet, ou un µprojet de
   ce projet corporate. */

const linksApi = {
  listMicroprojectLinks(filters) {
    return api.get(api.withQuery("/api/microproject-links", filters));
  },
  // body : { a, b, note } - a et b : slugs des deux µprojets
  createMicroprojectLink(body) {
    return api.post("/api/microproject-links", body);
  },
  removeMicroprojectLink(linkId) {
    return api.del(`/api/microproject-links/${encodeURIComponent(linkId)}`);
  },
  listEntityLinks(filters) {
    return api.get(api.withQuery("/api/entity-links", filters));
  },
  // body : { a, b, note } - a et b : { microproject, experiment_id, entity_index }
  createEntityLink(body) {
    return api.post("/api/entity-links", body);
  },
  removeEntityLink(linkId) {
    return api.del(`/api/entity-links/${encodeURIComponent(linkId)}`);
  },
};
