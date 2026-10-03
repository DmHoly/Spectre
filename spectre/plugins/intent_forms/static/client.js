/* Client de l'API du plugin intent_forms : formulaires d'intention d'un µprojet (les siens et ceux
   de la bibliothèque partagée) et formulaire actif. */

const intentFormsApi = {
  list(microprojectSlug) {
    return api.get(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/formulaires-intention`);
  },
  create(microprojectSlug, body) {
    return api.post(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/formulaires-intention`, body);
  },
  remove(microprojectSlug, name, shared) {
    return api.del(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/formulaires-intention/${encodeURIComponent(name)}?partagee=${Boolean(shared)}`);
  },
  active(microprojectSlug) {
    return api.get(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/formulaire-actif`);
  },
  // body : {name, partagee} ; {name: null} pour revenir au formulaire par défaut
  setActive(microprojectSlug, body) {
    return api.post(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/formulaire-actif`, body);
  },
};
