/* Client de l'API du plugin links : liens entre µprojets et entre entités physiques. */

const linksApi = {
  createMicroprojectLink(body) {
    return api.post("/api/liens-projets", body);
  },
  removeMicroprojectLink(linkId) {
    return api.del(`/api/liens-projets/${encodeURIComponent(linkId)}`);
  },
  createEntityLink(body) {
    return api.post("/api/liens-entites", body);
  },
  removeEntityLink(linkId) {
    return api.del(`/api/liens-entites/${encodeURIComponent(linkId)}`);
  },
};
