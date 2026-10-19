/* Client de l'API du plugin wafers : les plaques (recherche, celles d'un µprojet), le passeport
   d'une plaque, sa vie en ligne (suivi MES / Gozer), les plaques d'une FDL, et les fiches de plaque
   (les plaques d'avant Spectre : cherchées dans la base, enregistrées sans étude). */

const wafersApi = {
  // filters : {q, fdl, microproject} - q : un texte, ou plusieurs lasermarks (un tableau) -
  // [{key, lasermark, count, microprojects, latest, fdl, locations, record}] ; une fiche de plaque
  // sans étude : count 0, latest null, record {...}
  list(filters) {
    return api.get(api.withQuery("/api/wafers", filters));
  },
  // retrouver des plaques, dans Spectre puis dans la base, toutes d'un coup - {items: [{lasermark,
  // key, record, studies, microprojects, base}], source, base_error}
  lookup(lasermarks) {
    return api.get(api.withQuery("/api/wafers/lookup", { lasermark: lasermarks }));
  },
  // les fiches de ces plaques (créées, ou rendues telles quelles : `created`) - {items, source, base_error}
  createRecords(lasermarks) {
    return api.post("/api/wafer-records", { lasermarks });
  },
  // retire la fiche d'une plaque (son auteur, ou un administrateur) ; ses études restent
  deleteRecord(waferKey) {
    return api.del(`/api/wafer-records/${encodeURIComponent(waferKey)}`);
  },
  // waferKey : la clé d'une plaque, ou son lasermark tel qu'écrit
  get(waferKey) {
    return api.get(`/api/wafers/${encodeURIComponent(waferKey)}`);
  },
  // la vie d'une plaque en ligne (MES, Gozer, FDL, tests) et sa fraîcheur (meta) - lue des bases au
  // plus toutes les 24 h, plus jamais pour une plaque immobile depuis 30 jours
  tracking(waferKey) {
    return api.get(`/api/wafers/${encodeURIComponent(waferKey)}/tracking`);
  },
  // la frise de la plaque : {events: [{index, kind, at, end, label, detail, source, ref}], counts, svg}
  timeline(waferKey) {
    return api.get(`/api/wafers/${encodeURIComponent(waferKey)}/timeline`);
  },
  // relit les bases quoi qu'il arrive (le bouton « Rafraîchir »)
  refreshTracking(waferKey) {
    return api.post(`/api/wafers/${encodeURIComponent(waferKey)}/tracking/refresh`, {});
  },
  // attache une structure à la plaque, sans étude : {kind: "reference"|"saved", source_id, version}
  setStructure(waferKey, body) {
    return api.put(`/api/wafers/${encodeURIComponent(waferKey)}/structure`, body);
  },
  removeStructure(waferKey) {
    return api.del(`/api/wafers/${encodeURIComponent(waferKey)}/structure`);
  },
  // son contexte écrit sur sa page : {context, hypothesis, learnings} - tous vides : null
  setNotes(waferKey, body) {
    return api.put(`/api/wafers/${encodeURIComponent(waferKey)}/notes`, body);
  },
  // une plaque qui change de nom : {from_lasermark, to_lasermark, note, happened_at}
  createLink(body) {
    return api.post("/api/wafer-links", body);
  },
  deleteLink(linkId) {
    return api.del(`/api/wafer-links/${encodeURIComponent(linkId)}`);
  },
  // les plaques d'une FDL - {fdl, source, editable, known, wafers: [{lasermark, slot}]}
  fdl(fdl) {
    return api.get(`/api/fdls/${encodeURIComponent(fdl)}`);
  },
  // les plaques d'une FDL saisies à la main (base locale seulement) - lasermarks : dans l'ordre du lot
  setFdlWafers(fdl, lasermarks) {
    return api.put(`/api/fdls/${encodeURIComponent(fdl)}/wafers`, { lasermarks });
  },
};
