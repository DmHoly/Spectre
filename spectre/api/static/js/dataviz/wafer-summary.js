/* Synthèse par plaque : pour quelques KPI, le nombre de mesures, la médiane, la moyenne, l'écart
   type, le min et le max de chaque plaque - avec une barre qui situe la médiane d'une plaque par
   rapport aux autres. Le tableau qu'on recopie d'habitude dans la présentation. */
DataViz.register({
  key: "wafer-summary",
  label: "Synthèse par plaque",
  description: "Médiane, moyenne, écart type, min et max de quelques KPI, plaque par plaque.",
  accepts(ds, o = {}) {
    if (o.columns && o.columns.length) return o.columns.some((c) => DataViz.has(ds, c) && DataViz.kind(ds, c) === "number");
    return DataViz.columnsOfKind(ds, "number").length > 0;
  },
  options: () => [
    { key: "columns", label: "KPI", type: "columns", filter: "number" },
    { key: "hideZero", label: "Ignorer les zéros (devices éteints)", type: "checkbox" },
  ],
  defaults(ds) {
    const [x, y] = DataViz.xyColumns(ds);
    return { columns: DataViz.columnsOfKind(ds, "number").filter((c) => c !== x && c !== y).slice(0, 4) };
  },
  render(el, ds, o) {
    const columns = (o.columns || []).filter((c) => DataViz.has(ds, c) && DataViz.kind(ds, c) === "number");
    const groups = [...DataViz.byWafer(ds).entries()];
    const blocks = columns.map((c) => {
      const vs = DataViz.values(ds, c).map((v) => (o.hideZero && v === 0 ? null : v));
      const rows = groups.map(([wafer, idxs], gi) => ({ wafer, gi, st: DataViz.stats(idxs.map((i) => vs[i])) }));
      const medians = rows.filter((r) => r.st.n).map((r) => r.st.median);
      const [m0, m1] = DataViz.extent(medians);
      const bar = (v) => (m1 > m0 ? 12 + ((v - m0) / (m1 - m0)) * 88 : 100);
      return `
        <table class="viz-table viz-table--summary">
          <caption>${DataViz.esc(c)}</caption>
          <thead><tr><th scope="col">Plaque</th><th scope="col">n</th><th scope="col">Médiane</th><th scope="col">Moyenne</th><th scope="col">σ</th><th scope="col">Min</th><th scope="col">Max</th></tr></thead>
          <tbody>${rows
            .map((r) =>
              r.st.n
                ? `<tr>
                    <th scope="row"><span class="viz-legend__swatch" style="background:${DataViz.categorical(r.gi)}"></span><span class="mono">${DataViz.esc(r.wafer)}</span></th>
                    <td>${r.st.n}</td>
                    <td class="viz-table__median"><span class="viz-bar" style="width:${bar(r.st.median).toFixed(0)}%;background:${DataViz.categorical(r.gi)}"></span><strong>${DataViz.esc(DataViz.fmt(r.st.median))}</strong></td>
                    <td>${DataViz.esc(DataViz.fmt(r.st.mean))}</td>
                    <td>${DataViz.esc(DataViz.fmt(r.st.std))}</td>
                    <td>${DataViz.esc(DataViz.fmt(r.st.min))}</td>
                    <td>${DataViz.esc(DataViz.fmt(r.st.max))}</td>
                  </tr>`
                : `<tr><th scope="row" class="mono">${DataViz.esc(r.wafer)}</th><td colspan="6" class="viz-muted">aucune valeur</td></tr>`
            )
            .join("")}</tbody>
        </table>`;
    });
    el.innerHTML = blocks.length ? `<div class="viz-summary">${blocks.join("")}</div>` : `<div class="viz-empty">Choisissez au moins un KPI numérique.</div>`;
  },
});
