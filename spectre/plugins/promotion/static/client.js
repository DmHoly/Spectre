/* Client de l'API du plugin promotion : choisir une structure comme référence. Le corps d'une
   promotion : {microproject, experiment_id, version_id?, variant?, reference? | new_reference?
   {name, description}, parent?, note}. */

const promotionApi = {
  // ce que donnerait la promotion, sans rien écrire : {source, suggestion, target, parents, base,
  // level, level_text, number, rules: [{rule, label, level, message, code}], can_promote}
  preview(body) {
    return api.post("/api/promotions/preview", body);
  },
  // promouvoir -> la version de référence créée (refusée avec le message de la règle qui bloque)
  promote(body) {
    return api.post("/api/promotions", body);
  },
  // le journal, les plus récentes d'abord ; params : {microproject, experiment_id, limit}
  journal(params) {
    return api.get(api.withQuery("/api/promotions", params || {}));
  },
  // les µprojets où l'on peut promouvoir (éditeur) : [{slug, name}]
  sources() {
    return api.get("/api/promotion-sources");
  },
  // une brique comme brique de référence : {brick_id, note} -> {brick, rules, can_promote}
  previewBrick(body) {
    return api.post("/api/promotions/bricks/preview", body);
  },
  // promouvoir la brique -> la brique (partagée, avec sa référence) ; refusée avec la règle qui bloque
  promoteBrick(body) {
    return api.post("/api/promotions/bricks", body);
  },
};
