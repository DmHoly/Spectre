/* Client de l'API du plugin library : fichiers YAML de la bibliothèque de l'instance et textes
   d'interface (section « Objectifs et intention » du constructeur). */

const libraryApi = {
  listFiles() {
    return api.get("/api/library/files");
  },
  getFile(fileKey) {
    return api.get(`/api/library/files/${encodeURIComponent(fileKey)}`);
  },
  saveFile(fileKey, content) {
    return api.put(`/api/library/files/${encodeURIComponent(fileKey)}`, { content });
  },
  intentionTexts() {
    return api.get("/api/ui-texts/intention");
  },
};
