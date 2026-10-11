/* Client de l'API du plugin comparator : le tableau d'une comparaison de structures (une ligne par
   plaque, étude ou version de référence, chacune désignée par son jeton - voir Comparator.studyItem,
   waferItem, referenceItem dans comparator-table.js) et ce qu'on peut y ajouter pour une saisie. */

const comparatorApi = {
  // items : les jetons, dans l'ordre des lignes ; baseline : l'index de la ligne de base (0 par défaut)
  // -> {baseline, rows, groups, summary} ; une campagne donne une ligne par variante
  compare(items, baseline) {
    return api.get(api.withQuery("/api/comparisons", { item: items, baseline }));
  },
  // [{item, source, label, sublabel}] : plaques, études, versions de référence qui répondent à q
  candidates(q) {
    return api.get(api.withQuery("/api/comparison-candidates", { q }));
  },
};
