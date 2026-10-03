/* Client de l'API du plugin external_images : galerie d'images externes (TEM, scans) d'une
   expérience, parcours des dossiers autorisés et URL d'une image. */

const externalImagesApi = {
  create(microprojectSlug, ref, body) {
    return api.post(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(ref)}/data`, body);
  },
  remove(microprojectSlug, ref, itemId) {
    return api.del(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(ref)}/data/${encodeURIComponent(itemId)}`);
  },
  pin(microprojectSlug, ref, itemId, body) {
    return api.patch(
      `/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(ref)}/data/${encodeURIComponent(itemId)}/epingle`,
      body
    );
  },
  browse(microprojectSlug, folder) {
    return api.get(api.withQuery(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/data/parcourir`, { dossier: folder }));
  },
  imageUrl(microprojectSlug, path) {
    return `/api/microprojets/${encodeURIComponent(microprojectSlug)}/data/image?chemin=${encodeURIComponent(path)}`;
  },
};
