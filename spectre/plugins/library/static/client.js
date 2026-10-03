/* Client de l'API du plugin library : fichiers YAML de la bibliothèque de l'instance et textes
   d'interface (formulaire d'intention du constructeur). */

const libraryApi = {
  listFiles() {
    return api.get("/api/bibliotheque/fichiers");
  },
  getFile(key) {
    return api.get(`/api/bibliotheque/fichiers/${encodeURIComponent(key)}`);
  },
  saveFile(key, body) {
    return api.put(`/api/bibliotheque/fichiers/${encodeURIComponent(key)}`, body);
  },
  intentionForm(microprojectSlug) {
    return api.get(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/structures/intention-form`);
  },
};
