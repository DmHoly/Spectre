/* Client de l'API du plugin references : les références de structure de toute l'application, leurs
   versions MAJEUR.MINEUR (numéro calculé par le serveur) et les versions publiées depuis un µprojet. */

const referencesApi = {
  // toutes les références, la plus récemment mise à jour d'abord ; q : nom, slug, description
  list(q) {
    return api.get(api.withQuery("/api/references", { q }));
  },
  // {name, description} -> la référence, sans version (409 si le nom est déjà pris)
  create(body) {
    return api.post("/api/references", body);
  },
  // renommer ou décrire : {name, description} (son créateur ou un admin) ; le slug ne change pas
  update(referenceSlug, body) {
    return api.patch(`/api/references/${encodeURIComponent(referenceSlug)}`, body);
  },
  remove(referenceSlug) {
    return api.del(`/api/references/${encodeURIComponent(referenceSlug)}`);
  },
  // l'évolution d'une référence : {reference, lanes, nodes, edges}
  versions(referenceSlug) {
    return api.get(`/api/references/${encodeURIComponent(referenceSlug)}/versions`);
  },
  // publier une version d'étude : {microproject, experiment_id, version_id?, note?, parent?} -> la version
  // (son numéro calculé) ; 409 si elle est identique à sa version parente
  publish(referenceSlug, body) {
    return api.post(`/api/references/${encodeURIComponent(referenceSlug)}/versions`, body);
  },
  // une version (« 1.1 ») : son nœud, sa structure dessinée (structure_svg) et son procédé (process)
  version(referenceSlug, number) {
    return api.get(`/api/references/${encodeURIComponent(referenceSlug)}/versions/${encodeURIComponent(number)}`);
  },
  // la version comparée à `against` (une autre version de la référence), à sa parente par défaut
  versionDiff(referenceSlug, number, against) {
    return api.get(
      api.withQuery(`/api/references/${encodeURIComponent(referenceSlug)}/versions/${encodeURIComponent(number)}/structure-diff`, { against })
    );
  },
  // les versions de référence publiées depuis un µprojet (les badges « R nom 1.1 » de son évolution)
  publishedFrom(microprojectSlug) {
    return api.get(api.withQuery("/api/reference-versions", { microproject: microprojectSlug }));
  },
};
