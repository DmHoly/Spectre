/* Client de l'API du plugin notebook : instantanés de données d'un µprojet et vues du cahier de
   données d'une expérience. Les écritures sur le cahier envoient la version affichée (`versionId`,
   en-tête If-Match) : 412 si la piste a avancé entre-temps. Les types de données qu'on peut charger
   viennent de characterizationApi.list. */

const notebookApi = {
  // body : {hook, wafers, refresh}
  takeSnapshot(microprojectSlug, body) {
    return api.post(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/snapshots`, body);
  },
  snapshot(microprojectSlug, snapshotId) {
    return api.get(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/snapshots/${encodeURIComponent(snapshotId)}`);
  },
  // version : une version passée de la piste (la pointe sinon)
  entries(microprojectSlug, experimentId, version) {
    return api.get(
      api.withQuery(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/experiments/${encodeURIComponent(experimentId)}/notebook-entries`, { version })
    );
  },
  addEntry(microprojectSlug, experimentId, versionId, body) {
    return api.post(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/experiments/${encodeURIComponent(experimentId)}/notebook-entries`, body, {
      ifMatch: versionId && `"${versionId}"`,
    });
  },
  // body : les champs à changer ; {position} pour déplacer la vue
  updateEntry(microprojectSlug, experimentId, versionId, entryId, body) {
    return api.patch(
      `/api/microprojects/${encodeURIComponent(microprojectSlug)}/experiments/${encodeURIComponent(experimentId)}/notebook-entries/${encodeURIComponent(entryId)}`,
      body,
      { ifMatch: versionId && `"${versionId}"` }
    );
  },
  removeEntry(microprojectSlug, experimentId, versionId, entryId) {
    return api.del(
      `/api/microprojects/${encodeURIComponent(microprojectSlug)}/experiments/${encodeURIComponent(experimentId)}/notebook-entries/${encodeURIComponent(entryId)}`,
      { ifMatch: versionId && `"${versionId}"` }
    );
  },
};
