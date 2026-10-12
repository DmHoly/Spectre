/* Client de l'API du plugin references : les références de structure de toute l'application, leurs
   versions MAJEUR.MINEUR (numéro calculé par le serveur) et les versions publiées depuis un µprojet. */

const referencesApi = {
  // toutes les références, la plus récemment mise à jour d'abord ; q : nom, slug, description
  list(q) {
    return api.get(api.withQuery("/api/references", { q }));
  },
  // (créer une référence : le formulaire de la promotion, qui la crée avec sa première version)
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
  // (publier une version : le plugin promotion, promotionApi.promote)
  // une version (« 1.1 ») : son nœud, sa structure dessinée (structure_svg) et son procédé (process)
  version(referenceSlug, number) {
    return api.get(`/api/references/${encodeURIComponent(referenceSlug)}/versions/${encodeURIComponent(number)}`);
  },
  // les versions de référence publiées depuis un µprojet (les badges « R nom 1.1 » de son évolution)
  publishedFrom(microprojectSlug) {
    return api.get(api.withQuery("/api/reference-versions", { microproject: microprojectSlug }));
  },
};
