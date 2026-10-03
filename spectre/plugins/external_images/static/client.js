/* Client de l'API du plugin external_images : galerie d'images externes (TEM, scans) d'une
   expérience, parcours des dossiers autorisés et URL d'une image. Les écritures sur la galerie
   envoient la version affichée (`versionId`, en-tête If-Match) : 412 si la piste a avancé. */

const externalImagesApi = {
  create(microprojectSlug, experimentId, versionId, body) {
    return api.post(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(experimentId)}/data`, body, {
      ifMatch: versionId && `"${versionId}"`,
    });
  },
  remove(microprojectSlug, experimentId, versionId, itemId) {
    return api.del(
      `/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(experimentId)}/data/${encodeURIComponent(itemId)}`,
      { ifMatch: versionId && `"${versionId}"` }
    );
  },
  pin(microprojectSlug, experimentId, versionId, itemId, body) {
    return api.patch(
      `/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(experimentId)}/data/${encodeURIComponent(itemId)}/epingle`,
      body,
      { ifMatch: versionId && `"${versionId}"` }
    );
  },
  browse(microprojectSlug, folder) {
    return api.get(api.withQuery(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/data/parcourir`, { dossier: folder }));
  },
  imageUrl(microprojectSlug, path) {
    return `/api/microprojets/${encodeURIComponent(microprojectSlug)}/data/image?chemin=${encodeURIComponent(path)}`;
  },
};
