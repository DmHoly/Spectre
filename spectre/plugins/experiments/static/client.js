/* Client de l'API du plugin experiments : les études d'un µprojet. Une étude est une piste
   (`experimentId`, toujours sa dernière version) et ses versions (`versionId`). Chaque écriture sur
   une piste envoie la version affichée (`versionId`, en-tête If-Match) : si la piste a avancé
   entre-temps, la réponse est 412 et rien n'est écrit. Les écritures renvoient l'étude à jour. */

const experimentsApi = {
  // params : {status, q, offset, limit} -> {items, total}
  list(microprojectSlug, params) {
    return api.get(api.withQuery(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/experiments`, params));
  },
  // body : {structure: {kind: "process" | "images" | "campaign", ...}, title, intent, ..., from_version?, branch?}
  // ou, pour combiner deux études en une nouvelle : {merge_of: [{experiment_id, version_id?}, {...}], title, intent, entities, ...}
  create(microprojectSlug, body) {
    return api.post(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/experiments`, body);
  },
  get(microprojectSlug, experimentId) {
    return api.get(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/experiments/${encodeURIComponent(experimentId)}`);
  },
  getVersion(microprojectSlug, experimentId, versionId) {
    return api.get(
      `/api/microprojects/${encodeURIComponent(microprojectSlug)}/experiments/${encodeURIComponent(experimentId)}/versions/${encodeURIComponent(versionId)}`
    );
  },
  remove(microprojectSlug, experimentId, versionId) {
    return api.del(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/experiments/${encodeURIComponent(experimentId)}`, {
      ifMatch: versionId && `"${versionId}"`,
    });
  },
  // la frise : chaque version de la piste, de la première à la pointe (is_tip)
  versions(microprojectSlug, experimentId) {
    return api.get(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/experiments/${encodeURIComponent(experimentId)}/versions`);
  },
  // le procédé éditable d'une version (la pointe sans `version`)
  process(microprojectSlug, experimentId, version) {
    return api.get(
      api.withQuery(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/experiments/${encodeURIComponent(experimentId)}/process`, {
        version,
      })
    );
  },
  // params : {version, against_version, against_experiment, against_microproject} - sans cible, la
  // version de structure précédente
  structureDiff(microprojectSlug, experimentId, params) {
    return api.get(
      api.withQuery(
        `/api/microprojects/${encodeURIComponent(microprojectSlug)}/experiments/${encodeURIComponent(experimentId)}/structure-diff`,
        params
      )
    );
  },
  // les variantes d'une campagne (structures en SVG, libellés, facteurs)
  variants(microprojectSlug, experimentId, version) {
    return api.get(
      api.withQuery(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/experiments/${encodeURIComponent(experimentId)}/variants`, {
        version,
      })
    );
  },
  // une nouvelle version de la piste : body = {structure: {kind: "process" | "images", ...}, title, intent, ...}
  evolve(microprojectSlug, experimentId, versionId, body) {
    return api.post(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/experiments/${encodeURIComponent(experimentId)}/versions`, body, {
      ifMatch: versionId && `"${versionId}"`,
    });
  },
  replaceStructureImages(microprojectSlug, experimentId, versionId, body) {
    return api.put(
      `/api/microprojects/${encodeURIComponent(microprojectSlug)}/experiments/${encodeURIComponent(experimentId)}/structure-images`,
      body,
      { ifMatch: versionId && `"${versionId}"` }
    );
  },
  // body : {status: "draft" | "running" | "hold", hold_reason}
  setStatus(microprojectSlug, experimentId, versionId, body) {
    return api.put(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/experiments/${encodeURIComponent(experimentId)}/status`, body, {
      ifMatch: versionId && `"${versionId}"`,
    });
  },
  conclude(microprojectSlug, experimentId, versionId, body) {
    return api.put(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/experiments/${encodeURIComponent(experimentId)}/conclusion`, body, {
      ifMatch: versionId && `"${versionId}"`,
    });
  },
  setTags(microprojectSlug, experimentId, versionId, body) {
    return api.put(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/experiments/${encodeURIComponent(experimentId)}/tags`, body, {
      ifMatch: versionId && `"${versionId}"`,
    });
  },
  setEntities(microprojectSlug, experimentId, versionId, body) {
    return api.put(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/experiments/${encodeURIComponent(experimentId)}/entities`, body, {
      ifMatch: versionId && `"${versionId}"`,
    });
  },
  // renommer une ref (sa version ne change pas) : 409 si le nom est pris
  renameRef(microprojectSlug, refName, newName) {
    return api.patch(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/refs/${encodeURIComponent(refName)}`, { name: newName });
  },
  // retirer une ref ; la version reste
  deleteRef(microprojectSlug, refName) {
    return api.del(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/refs/${encodeURIComponent(refName)}`);
  },
  // l'évolution des structures, piste par piste : {lanes, nodes, edges} ; allVersions : les
  // versions légères aussi (correctifs, versions sans changement de structure) ; includeVersions :
  // des ids de version à montrer en plus (les versions publiées comme référence)
  structureHistory(microprojectSlug, allVersions, includeVersions) {
    return api.get(
      api.withQuery(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/structure-history`, {
        all_versions: allVersions ? "true" : undefined,
        include_versions: includeVersions || [],
      })
    );
  },
  lineage(microprojectSlug) {
    return api.get(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/lineage`);
  },
  // les compteurs de chaque µprojet : filters = {area, microproject} (slugs, facultatifs)
  stats(filters) {
    return api.get(api.withQuery("/api/experiment-stats", filters));
  },
  // la frise des µprojets d'un projet : filters = {area, thematic}
  timeline(filters) {
    return api.get(api.withQuery("/api/experiment-timeline", filters));
  },
};
