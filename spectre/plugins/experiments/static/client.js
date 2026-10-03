/* Client de l'API du plugin experiments : expériences d'un µprojet (lancement, évolution, statut,
   conclusion, étiquettes, entités, fusion, suppression), diff, filiation et refs. `ref` : l'id
   d'une expérience. */

const experimentsApi = {
  // params : {status, q, offset, limit}
  list(microprojectSlug, params) {
    return api.get(api.withQuery(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences`, params));
  },
  launch(microprojectSlug, body) {
    return api.post(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences`, body);
  },
  launchImage(microprojectSlug, body) {
    return api.post(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/image`, body);
  },
  launchCampaign(microprojectSlug, body) {
    return api.post(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/campagne`, body);
  },
  get(microprojectSlug, ref) {
    return api.get(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(ref)}`);
  },
  remove(microprojectSlug, ref) {
    return api.del(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(ref)}`);
  },
  timeline(microprojectSlug, ref) {
    return api.get(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(ref)}/timeline`);
  },
  process(microprojectSlug, ref) {
    return api.get(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(ref)}/process`);
  },
  // la structure comparée à sa version précédente, ou à l'expérience `against` du même µprojet
  diff(microprojectSlug, ref, against) {
    return api.get(
      api.withQuery(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(ref)}/diff`, { against })
    );
  },
  // la structure comparée à celle d'une expérience d'un autre µprojet
  diffExternal(microprojectSlug, ref, otherMicroprojectSlug, otherRef) {
    return api.get(
      api.withQuery(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(ref)}/diff-externe`, {
        autre_projet: otherMicroprojectSlug,
        autre_experience: otherRef,
      })
    );
  },
  // les variantes d'une campagne (structures en SVG, libellés, facteurs)
  variants(microprojectSlug, ref) {
    return api.get(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(ref)}/matrice`);
  },
  evolve(microprojectSlug, ref, body) {
    return api.post(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(ref)}/evoluer`, body);
  },
  evolveWithImage(microprojectSlug, ref, body) {
    return api.post(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(ref)}/evoluer-image`, body);
  },
  replaceDrawing(microprojectSlug, ref, body) {
    return api.post(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(ref)}/dessin`, body);
  },
  setStatus(microprojectSlug, ref, body) {
    return api.post(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(ref)}/statut`, body);
  },
  conclude(microprojectSlug, ref, body) {
    return api.post(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(ref)}/conclure`, body);
  },
  setTags(microprojectSlug, ref, body) {
    return api.post(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(ref)}/etiquettes`, body);
  },
  setEntities(microprojectSlug, ref, body) {
    return api.post(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(ref)}/entites`, body);
  },
  combine(microprojectSlug, ref, body) {
    return api.post(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(ref)}/combiner`, body);
  },
  createRef(microprojectSlug, ref, body) {
    return api.post(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(ref)}/ref`, body);
  },
  lineage(microprojectSlug) {
    return api.get(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/filiation`);
  },
  refsGraph(microprojectSlug) {
    return api.get(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/refs/graphe`);
  },
  // les compteurs de chaque µprojet : filters = {area, microproject} (slugs, facultatifs)
  stats(filters) {
    return api.get(api.withQuery("/api/experiment-stats", filters));
  },
  // la frise des µprojets d'un projet : filters = {area, thematic}
  timeline(filters) {
    return api.get(api.withQuery("/api/experiment-timeline", filters));
  },
};
