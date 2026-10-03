/* Client de l'API du plugin intent_forms : la bibliothèque de formulaires d'intention (à plat :
   chaque entrée porte son id et sa portée, shared ou microproject) et le formulaire actif d'un
   µprojet (une copie de l'entrée activée, avec son origine et `outdated`). */

const intentFormsApi = {
  // params : {microproject, scope} - la bibliothèque partagée, plus celle du µprojet s'il est donné
  list(params) {
    return api.get(api.withQuery("/api/intent-forms", params));
  },
  // body : {name, yaml, scope: "shared" | "microproject", microproject}
  create(body) {
    return api.post("/api/intent-forms", body);
  },
  // body : {name} et/ou {yaml}
  update(formId, body) {
    return api.patch(`/api/intent-forms/${encodeURIComponent(formId)}`, body);
  },
  remove(formId) {
    return api.del(`/api/intent-forms/${encodeURIComponent(formId)}`);
  },
  // Le formulaire actif {form, origin, outdated}, ou null si le µprojet n'en a pas (404).
  getActive(microprojectSlug) {
    return api.get(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/active-intent-form`).catch((err) => {
      if (err.status === 404 && err.data && err.data.code === "no_active_intent_form") return null;
      throw err;
    });
  },
  activate(microprojectSlug, intentFormId) {
    return api.put(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/active-intent-form`, { intent_form_id: intentFormId });
  },
  deactivate(microprojectSlug) {
    return api.del(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/active-intent-form`);
  },
};
