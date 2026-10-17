/* Client de l'API du plugin wafer_data : les blocs de la fiche data d'un projet corporate, la fiche data d'une
   plaque, le calcul d'avance des fiches d'un projet et ce que pèse leur magasin. */

const waferDataApi = {
  // {hooks: [{hook, title, category, columns: [{name, unit, description, type, sure, chosen, observed_type, guessed,
  //  example}], x, y, dated, representative, observed_at}], types, roles, kinds, aggregates, curve_modes, placeholders, limits}
  catalog(areaSlug) {
    return api.get(`/api/areas/${encodeURIComponent(areaSlug)}/wafer-data/catalog`);
  },
  // lit le type de données sur une plaque (ou quelques plaques suivies du projet) : rend le type à jour
  probe(areaSlug, hook, lasermark = null) {
    return api.post(`/api/areas/${encodeURIComponent(areaSlug)}/wafer-data/catalog/${encodeURIComponent(hook)}/probe`, lasermark ? { lasermark } : {});
  },
  // type null : revenir au type observé ou deviné ; vaut pour tous les projets
  setColumnType(areaSlug, hook, column, type) {
    return api.put(`/api/areas/${encodeURIComponent(areaSlug)}/wafer-data/catalog/${encodeURIComponent(hook)}/columns`, { column, type });
  },
  // [{id, kind, kind_label, hook, hook_title, available, config, label, title, unit, position}]
  blocks(areaSlug) {
    return api.get(`/api/areas/${encodeURIComponent(areaSlug)}/wafer-data/blocks`);
  },
  // {kind, hook, config, label?} -> 201 ; gérer le projet
  add(areaSlug, body) {
    return api.post(`/api/areas/${encodeURIComponent(areaSlug)}/wafer-data/blocks`, body);
  },
  // {label?} et/ou {config?} et/ou {move: "up" | "down"}
  update(areaSlug, blockId, body) {
    return api.patch(`/api/areas/${encodeURIComponent(areaSlug)}/wafer-data/blocks/${encodeURIComponent(blockId)}`, body);
  },
  remove(areaSlug, blockId) {
    return api.del(`/api/areas/${encodeURIComponent(areaSlug)}/wafer-data/blocks/${encodeURIComponent(blockId)}`);
  },
  // un paquet de plaques du projet : {total, done, next_offset, computed, errors, source}
  compute(areaSlug, { offset = 0, refresh = false } = {}) {
    return api.post(api.withQuery(`/api/areas/${encodeURIComponent(areaSlug)}/wafer-data/compute`, { offset, refresh: refresh || undefined }), {});
  },
  // {wafer, source, areas: [{area, can_manage, microprojects, blocks: [{..., status, message, computed_at, data, population?}]}]}
  sheet(lasermark, { refresh = false } = {}) {
    return api.get(api.withQuery(`/api/wafers/${encodeURIComponent(lasermark)}/data`, { refresh: refresh || undefined }));
  },
  // {digests, wafers, scalars, payload_bytes, file_bytes, budget_bytes} - administrateurs
  storage() {
    return api.get("/api/wafer-data/storage");
  },
};
