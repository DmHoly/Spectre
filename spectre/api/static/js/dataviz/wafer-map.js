/* Carte wafer : une carte par plaque, chaque point de mesure (ou device) à sa position X/Y, coloré
   selon la valeur choisie - même échelle de couleurs pour toutes les plaques, pour qu'on les
   compare d'un coup d'œil. Survol : position et valeur. Pour tout type de données qui porte des
   coordonnées sur la plaque (EQE par device, cartographie PL, NCEL...). */
DataViz.register({
  key: "wafer-map",
  label: "Carte wafer",
  description: "Une carte par plaque, chaque point coloré selon une valeur - même échelle pour toutes.",
  accepts(ds, o = {}) {
    const [x, y] = DataViz.xyColumns(ds);
    if (!x || !y || DataViz.kind(ds, x) !== "number" || DataViz.kind(ds, y) !== "number") return false;
    if (o.value) return DataViz.has(ds, o.value) && DataViz.kind(ds, o.value) === "number";
    return DataViz.columnsOfKind(ds, "number").length > 2;
  },
  options: () => [
    { key: "value", label: "Valeur", type: "column", filter: "number" },
    { key: "log", label: "Échelle de couleurs logarithmique", type: "checkbox" },
    { key: "perWafer", label: "Une échelle par plaque", type: "checkbox" },
    { key: "hideZero", label: "Zéros à part (devices éteints)", type: "checkbox" },
  ],
  defaults(ds) {
    const [x, y] = DataViz.xyColumns(ds);
    const numbers = DataViz.columnsOfKind(ds, "number").filter((c) => c !== x && c !== y);
    return { value: numbers[0], log: false, perWafer: false, hideZero: false };
  },
  render(el, ds, o) {
    const [xc, yc] = DataViz.xyColumns(ds);
    const xs = DataViz.values(ds, xc);
    const ys = DataViz.values(ds, yc);
    // « zéros à part » : un device éteint (EQE 0...) en gris, hors de l'échelle de couleurs
    const vs = DataViz.values(ds, o.value).map((v) => (o.hideZero && v === 0 ? null : v));
    const zeros = o.hideZero ? DataViz.values(ds, o.value).map((v) => v === 0) : [];
    const step = (list) => {
      const u = [...new Set(list.filter((v) => typeof v === "number"))].sort((a, b) => a - b);
      let best = Infinity;
      for (let i = 1; i < u.length; i++) best = Math.min(best, u[i] - u[i - 1]);
      return Number.isFinite(best) && best > 0 ? best : 1;
    };
    const [x0, x1] = DataViz.extent(xs);
    const [y0, y1] = DataViz.extent(ys);
    const sxStep = step(xs);
    const syStep = step(ys);
    const cols = Math.round((x1 - x0) / sxStep) + 1;
    const rowsN = Math.round((y1 - y0) / syStep) + 1;
    const size = 220;
    const cell = Math.max(2, Math.min(size / cols, size / rowsN));
    const width = cols * cell;
    const height = rowsN * cell;
    const toT = (range, v) => {
      if (typeof v !== "number" || !Number.isFinite(v)) return null;
      if (o.log) {
        if (v <= 0 || range[0] <= 0) return null;
        return (Math.log10(v) - Math.log10(range[0])) / (Math.log10(range[1]) - Math.log10(range[0]) || 1);
      }
      return (v - range[0]) / (range[1] - range[0] || 1);
    };
    const global = DataViz.extent(o.log ? vs.filter((v) => v > 0) : vs);
    const groups = DataViz.byWafer(ds);
    const maps = [...groups.entries()].map(([wafer, idxs]) => {
      const local = DataViz.extent(idxs.map((i) => vs[i]).filter((v) => !o.log || v > 0));
      const range = o.perWafer ? local : global;
      const st = DataViz.stats(idxs.map((i) => vs[i]));
      const rects = idxs
        .map((i) => {
          if (typeof xs[i] !== "number" || typeof ys[i] !== "number") return "";
          const cx = ((xs[i] - x0) / sxStep) * cell;
          const cy = ((y1 - ys[i]) / syStep) * cell; // Y vers le haut, comme sur la plaque
          const v = vs[i];
          const tipText = `${wafer} · X ${DataViz.fmt(xs[i])}, Y ${DataViz.fmt(ys[i])} · ${o.value} ${zeros[i] ? "0 (éteint)" : v === null || v === undefined ? "—" : DataViz.fmt(v)}`;
          return `<rect x="${cx.toFixed(2)}" y="${cy.toFixed(2)}" width="${(cell * 0.94).toFixed(2)}" height="${(cell * 0.94).toFixed(2)}" rx="${Math.min(2, cell / 5).toFixed(2)}" fill="${DataViz.sequential(toT(range, v))}" data-tip="${DataViz.esc(tipText)}"/>`;
        })
        .join("");
      const legend = o.perWafer ? `<div class="viz-map__range mono">${DataViz.esc(DataViz.fmt(range[0]))} – ${DataViz.esc(DataViz.fmt(range[1]))}</div>` : "";
      return `
        <figure class="viz-map">
          <figcaption class="viz-map__title"><span class="mono">${DataViz.esc(wafer)}</span><span class="viz-map__stat">médiane ${st.n ? DataViz.esc(DataViz.fmt(st.median)) : "—"}${o.hideZero && idxs.some((i) => zeros[i]) ? ` · ${idxs.filter((i) => zeros[i]).length} éteints` : ""}</span></figcaption>
          ${DataViz.svgOpen(width + 4, height + 4, `Carte ${wafer} : ${o.value}`)}<g transform="translate(2,2)">${rects}</g></svg>
          ${legend}
        </figure>`;
    });
    el.innerHTML = `
      <div class="viz-maps">${maps.join("")}</div>
      ${
        o.perWafer
          ? ""
          : `<div class="viz-colorbar"><span class="mono">${DataViz.esc(DataViz.fmt(global[0]))}</span><span class="viz-colorbar__ramp" style="background:${DataViz.gradientCss()}"></span><span class="mono">${DataViz.esc(DataViz.fmt(global[1]))}</span><span class="viz-colorbar__label">${DataViz.esc(o.value)}${o.log ? " (log)" : ""}</span></div>`
      }`;
  },
});
