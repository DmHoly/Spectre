/* Client de l'API du plugin external_images : galerie d'images externes (TEM, scans) d'une
   expérience et parcours des dossiers autorisés. Chaque image d'un jeu porte son `url` (le chemin
   reste côté serveur). Les écritures sur la galerie envoient la version affichée (`versionId`,
   en-tête If-Match) : 412 si la piste a avancé. */

const externalImagesApi = {
  // version : une version passée de la piste (la pointe sinon)
  list(microprojectSlug, experimentId, version) {
    return api.get(
      api.withQuery(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/experiments/${encodeURIComponent(experimentId)}/image-sets`, { version })
    );
  },
  // body : {title, note, entity_index, image_paths, pinned_index}
  create(microprojectSlug, experimentId, versionId, body) {
    return api.post(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/experiments/${encodeURIComponent(experimentId)}/image-sets`, body, {
      ifMatch: versionId && `"${versionId}"`,
    });
  },
  pin(microprojectSlug, experimentId, versionId, setId, pinnedIndex) {
    return api.patch(
      `/api/microprojects/${encodeURIComponent(microprojectSlug)}/experiments/${encodeURIComponent(experimentId)}/image-sets/${encodeURIComponent(setId)}`,
      { pinned_index: pinnedIndex },
      { ifMatch: versionId && `"${versionId}"` }
    );
  },
  remove(microprojectSlug, experimentId, versionId, setId) {
    return api.del(
      `/api/microprojects/${encodeURIComponent(microprojectSlug)}/experiments/${encodeURIComponent(experimentId)}/image-sets/${encodeURIComponent(setId)}`,
      { ifMatch: versionId && `"${versionId}"` }
    );
  },
  // les images d'un dossier autorisé : [{name, path, size, displayable}]
  browse(microprojectSlug, directory) {
    return api.get(api.withQuery(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/external-images`, { directory }));
  },
};
