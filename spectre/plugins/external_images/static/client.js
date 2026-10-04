/* Client de l'API du plugin external_images : choisir des images externes (TEM, scans) sur le disque
   du serveur, sans les copier - les dossiers autorisés d'où partir, puis les images d'un dossier. Les
   images choisies sont un contenu d'une mesure du cahier (notebookApi), qui les sert par son `url`. */

const externalImagesApi = {
  // les dossiers autorisés, tels qu'écrits dans SPECTRE_EXTERNAL_IMAGE_ROOTS : [chemin] ; vide, le
  // parcours est désactivé sur ce serveur
  roots(microprojectSlug) {
    return api.get(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/external-images/roots`);
  },
  // les images d'un dossier autorisé : [{name, path, size, displayable}] (un TIFF : displayable false)
  browse(microprojectSlug, directory) {
    return api.get(api.withQuery(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/external-images`, { directory }));
  },
};
