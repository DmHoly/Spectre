/* Client de l'API du plugin notebook : instantanés de données d'un µprojet et entrées du cahier de
   données d'une expérience (PRISM ou manuelles). Les écritures sur le cahier envoient la version
   affichée (`versionId`, en-tête If-Match) : 412 si la piste a avancé entre-temps. Les types de
   données qu'on peut charger viennent de characterizationApi.list ; les fichiers d'une entrée
   manuelle se téléversent d'abord (attachmentsApi.upload, purpose "notebook"). */

const notebookApi = {
  // body : {hook, wafers, refresh}
  takeSnapshot(microprojectSlug, body) {
    return api.post(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/snapshots`, body);
  },
  snapshot(microprojectSlug, snapshotId) {
    return api.get(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/snapshots/${encodeURIComponent(snapshotId)}`);
  },
  // version : une version passée de la piste (la pointe sinon) ; filters : {step, wafer, kind} -
  // [{id, kind, title, note, objective, interpretation, wafers, applies, in_report, measurements:
  // [{step_id, step_retired, ...}], created_at, created_by, updated_at, updated_by}]
  entries(microprojectSlug, experimentId, version, filters = {}) {
    return api.get(
      api.withQuery(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/experiments/${encodeURIComponent(experimentId)}/notebook-entries`, {
        version,
        ...filters,
      })
    );
  },
  // {step_id: n} : pour chaque étape, le nombre d'entrées qui s'appliquent à la version et y ont une
  // mesure (les badges de la vue du procédé)
  stepCounts(microprojectSlug, experimentId, version) {
    return api.get(
      api.withQuery(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/experiments/${encodeURIComponent(experimentId)}/notebook-entries`, {
        version,
        summary: "steps",
      })
    );
  },
  // body : {kind: "prism" | "manual", title, note, objective, interpretation, wafers, measurements, in_report}
  addEntry(microprojectSlug, experimentId, versionId, body) {
    return api.post(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/experiments/${encodeURIComponent(experimentId)}/notebook-entries`, body, {
      ifMatch: versionId && `"${versionId}"`,
    });
  },
  // body : les champs à changer (measurements : toutes les mesures) ; {position} pour déplacer l'entrée
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
