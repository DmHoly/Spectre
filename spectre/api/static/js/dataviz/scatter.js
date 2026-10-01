/* Nuage de points : une grandeur contre une autre (EQE max contre longueur d'onde, PL intégrée
   contre FWHM...), un point par ligne, coloré par plaque. */
DataViz.register({
  key: "scatter",
  label: "Nuage de points",
  description: "Une grandeur contre une autre, un point par mesure, coloré par plaque.",
  accepts(ds, o = {}) {
    if (o.x || o.y) return [o.x, o.y].every((c) => !c || (DataViz.has(ds, c) && DataViz.kind(ds, c) === "number"));
    return DataViz.columnsOfKind(ds, "number").length >= 2;
  },
  options: () => [
    { key: "x", label: "Axe horizontal", type: "column", filter: "number" },
    { key: "y", label: "Axe vertical", type: "column", filter: "number" },
    { key: "logx", label: "Horizontal en log", type: "checkbox" },
    { key: "logy", label: "Vertical en log", type: "checkbox" },
  ],
  defaults(ds) {
    const [xc, yc] = DataViz.xyColumns(ds);
    const numbers = DataViz.columnsOfKind(ds, "number").filter((c) => c !== xc && c !== yc);
    return { x: numbers[1] || numbers[0], y: numbers[0], logx: false, logy: false };
  },
  render(el, ds, o) {
    const xs = DataViz.values(ds, o.x);
    const ys = DataViz.values(ds, o.y);
    const ok = (v, log) => typeof v === "number" && Number.isFinite(v) && (!log || v > 0);
    const W = 720;
    const H = 360;
    const frame = { left: 70, top: 14, width: W - 90, height: H - 64 };
    const xsOk = xs.filter((v) => ok(v, o.logx));
    const ysOk = ys.filter((v) => ok(v, o.logy));
    if (!xsOk.length || !ysOk.length) {
      el.innerHTML = `<div class="viz-empty">Pas de valeurs numériques à croiser.</div>`;
      return;
    }
    const sx = DataViz.scale(DataViz.padded(DataViz.extent(xsOk), o.logx), [frame.left, frame.left + frame.width], { log: o.logx });
    const sy = DataViz.scale(DataViz.padded(DataViz.extent(ysOk), o.logy), [frame.top + frame.height, frame.top], { log: o.logy });
    const groups = [...DataViz.byWafer(ds).entries()];
    let dots = "";
    groups.forEach(([wafer, idxs], gi) => {
      const c = DataViz.categorical(gi);
      idxs.forEach((i) => {
        if (!ok(xs[i], o.logx) || !ok(ys[i], o.logy)) return;
        dots += `<circle cx="${sx(xs[i]).toFixed(1)}" cy="${sy(ys[i]).toFixed(1)}" r="3" fill="${c}" fill-opacity="0.55" data-tip="${DataViz.esc(`${wafer} · ${o.x} ${DataViz.fmt(xs[i])} · ${o.y} ${DataViz.fmt(ys[i])}`)}"/>`;
      });
    });
    el.innerHTML = `${DataViz.svgOpen(W, H, `${o.y} en fonction de ${o.x}`)}
      ${DataViz.axes(frame, sx, sy, { xLabel: o.x + (o.logx ? " (log)" : ""), yLabel: o.y + (o.logy ? " (log)" : "") })}
      ${dots}</svg>${DataViz.legendHtml(groups.map(([w]) => w))}`;
  },
});
