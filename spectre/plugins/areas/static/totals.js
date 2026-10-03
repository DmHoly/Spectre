/* Les compteurs cumulés d'une liste de µprojets (lignes de experimentsApi.stats : {microproject,
   running, concluded, abandoned, wafers}) - ceux d'un projet, d'une thématique, de l'accueil.
   « terminées » = conclues ou abandonnées. Les wafers s'additionnent d'un µprojet à l'autre. */

function experimentTotals(rows) {
  const totals = { microprojects: rows.length, experiments: 0, running: 0, done: 0, wafers: 0 };
  for (const row of rows) {
    totals.running += row.running;
    totals.done += row.concluded + row.abandoned;
    totals.wafers += row.wafers;
  }
  totals.experiments = totals.running + totals.done;
  return totals;
}
