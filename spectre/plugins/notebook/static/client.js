/* Client de l'API du plugin notebook : sources de données d'un µprojet, instantanés, et vues du
   cahier de données d'une expérience. */

const notebookApi = {
  sources(microprojectSlug) {
    return api.get(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/donnees/sources`);
  },
  takeSnapshot(microprojectSlug, body) {
    return api.post(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/donnees/instantanes`, body);
  },
  snapshot(microprojectSlug, snapshotId) {
    return api.get(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/donnees/instantanes/${encodeURIComponent(snapshotId)}`);
  },
  addEntry(microprojectSlug, ref, body) {
    return api.post(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(ref)}/cahier`, body);
  },
  updateEntry(microprojectSlug, ref, entryId, body) {
    return api.put(
      `/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(ref)}/cahier/${encodeURIComponent(entryId)}`,
      body
    );
  },
  removeEntry(microprojectSlug, ref, entryId) {
    return api.del(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(ref)}/cahier/${encodeURIComponent(entryId)}`);
  },
};
