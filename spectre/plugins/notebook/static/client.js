/* Client de l'API du plugin notebook : sources de données d'un µprojet, instantanés, et vues du
   cahier de données d'une expérience. Les écritures sur le cahier envoient la version affichée
   (`versionId`, en-tête If-Match) : 412 si la piste a avancé entre-temps. */

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
  addEntry(microprojectSlug, experimentId, versionId, body) {
    return api.post(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(experimentId)}/cahier`, body, {
      ifMatch: versionId && `"${versionId}"`,
    });
  },
  updateEntry(microprojectSlug, experimentId, versionId, entryId, body) {
    return api.put(
      `/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(experimentId)}/cahier/${encodeURIComponent(entryId)}`,
      body,
      { ifMatch: versionId && `"${versionId}"` }
    );
  },
  removeEntry(microprojectSlug, experimentId, versionId, entryId) {
    return api.del(
      `/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(experimentId)}/cahier/${encodeURIComponent(entryId)}`,
      { ifMatch: versionId && `"${versionId}"` }
    );
  },
};
